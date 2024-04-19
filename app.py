import os
from datetime import datetime

from flask import Flask, render_template, request, jsonify, url_for, flash, redirect
import requests
import json
import xml.etree.ElementTree as ET

from requests import RequestException

app = Flask(__name__)

@app.route('/')
def index():
    """
    Render the index.html template with app_config.json data.
    """
    # Get the URL for app_config.json
    app_config_url = url_for('static', filename='app_config.json')
    with open(f'static/config/app_config.json') as f:
        app_config = json.load(f)
    return render_template('index.html', app_config=app_config)

UPLOAD_FOLDER = 'static/config'
ALLOWED_EXTENSIONS = {'json'}

def preprocess_json(json_string):
    # Replace single backslashes with double backslashes
    return json_string.replace('\\', '\\\\')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_json(data):
    required_keys = ['serviceName', 'operationName', 'useCase', 'successCriteria', 'endpoint', 'headers','sampleRequestLocation']
    entries_with_missing_keys = {}
    # Check if 'entries' key exists
    if 'entries' not in data:
        return False, {'error': 'The JSON file does not seem correct. Please recheck.'}

    for entry in data['entries']:

        # Preprocess sampleRequestLocation
        if 'sampleRequestLocation' in entry:
            entry['sampleRequestLocation'] = preprocess_json(entry['sampleRequestLocation'])

        missing_keys = [key for key in required_keys if key not in entry]
        if missing_keys:
            entries_with_missing_keys[entry.get('operationName', 'UnknownOperation')] = missing_keys

    if entries_with_missing_keys:
        return False, entries_with_missing_keys
    else:
        return True, {}

def backup_config(file_path):
    original_path = file_path #os.path.join(UPLOAD_FOLDER, 'config.json')
    filename_without_extension = os.path.splitext(os.path.basename(file_path))[0]

    timestamp = datetime.now().strftime("%Y%m%d%S")
    backup_path = os.path.join(UPLOAD_FOLDER, f'backup/{filename_without_extension}_{timestamp}.json')
    if os.path.exists(original_path):
        try:
            os.rename(original_path, backup_path)
            return True
        except Exception as e:
            print(f"Error while creating backup: {e}")
            return False
    else:
        return True

@app.route('/upload',  methods=['GET', 'POST'])
def upload():
    APP_CONFIG_FILE = 'static/config/app_config.json'

    if request.method == 'GET':
        return render_template('upload_config.html')

    else:
        # print("Received Form Data:", request.form)  # Debugging line
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': ' No config file was provided '}), 500
            # return redirect(request.url)
        file = request.files['file']

        # app_name = request.form['appName']
        app_name = request.form.get('appName')

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            try:
                data = json.loads(file.read())
            except json.JSONDecodeError as e:
                return jsonify({'status': 'error', 'message': 'Invalid JSON format'}), 500
            is_valid_json, missing_keys = validate_json(data)
            if is_valid_json:

                file_path = os.path.join('static/config',
                                         f"{app_name.lower().replace(' ', '_')}_config_file.json").replace('\\',
                                                                                                           '/')
                # Update app_config.json
                with open(APP_CONFIG_FILE, 'r+') as f:
                    data = json.load(f)
                    # Check if app_name already exists
                    existing_apps = [app['name'] for app in data['applications']]
                    if app_name not in existing_apps:
                       # return jsonify({'status': 'error', 'message': 'Application name already exists'}), 500
                        data['applications'].append({
                            'name': app_name,
                            'file': file_path
                        })
                        f.seek(0)
                        json.dump(data, f, indent=4)

                backup_successful = backup_config(file_path)
                if not backup_successful:
                    return jsonify({'status': 'error', 'message': 'Error creating backup'}), 500
                filename = 'config.json'
                file.seek(0)  # Reset file pointer to start before saving



                # file.save(os.path.join(UPLOAD_FOLDER, filename))
                file.save(file_path)
                print(file_path)

                return jsonify({'status': 'success', 'message': 'File uploaded successfully'}), 200
            else:
                error_message = f'Invalid JSON structure. Missing keys for operations: {missing_keys}'
                return jsonify({'status': 'error', 'message': error_message}), 500
                # return jsonify({'status': 'error',
                #                 'message': 'Invalid JSON structure. Missing one or more required keys in "entries".'}), 500
        else:
            return jsonify({'status': 'error', 'message': 'Invalid file format. Only JSON files are allowed.'}), 500
    return render_template('upload_config.html')



@app.route('/execute', methods=['POST'])
def execute():
    """
    Execute the selected services based on the provided JSON configuration.
    """
    try:
        data = request.get_json()  # Parse JSON data from request
        selected_services = data.get('services', [])
        targetJson = data.get('targetJson','')
        iteration_count = int(data.get('iterationCount', 1))  # Default to 1 if not provided
        #print(data)

        # Load configuration from static.json
        if not targetJson:
            return jsonify({'status': 'error', 'message': 'No target JSON config found!'})

        with open(targetJson) as f:
            config = json.load(f)


        # Populate services list from static
        services = []
        for entry in config['entries']:
            services.append(entry['serviceName'])

        if not selected_services:
            return jsonify({'status': 'error', 'message': 'No services selected!'})

        result = {'status': 'success', 'responses': {}}
        for service in selected_services:
            service_parts = service.split(':')  # Split ServiceName:OperationName into parts
            if len(service_parts) != 2:
                return jsonify({'status': 'error', 'message': 'Invalid service format: ' + service})

            service_name, operation_name = service_parts  # Extract ServiceName and OperationName

            responses = []
            status_descriptions = []  # List to store response codes

            overall_status = 'GREEN'  # Assume GREEN initially
            passed_count = 0  # Counter for passed iterations
            raw_requests = []  # List to store raw requests
            for entry in config['entries']:
                if entry['serviceName'] == service_name and entry.get(
                        'operationName') == operation_name:  # Check both ServiceName and OperationName

                    method = 'GET' if entry.get('sampleRequestLocation') == '' else 'POST'
                    headers = entry.get('headers', {})
                    request_executed = False
                    processed_requests = set()
                    # Check if the service name and operation name combination has been processed
                    service_operation_key = (entry['serviceName'], entry.get('operationName', ''))

                    for i in range(iteration_count):  # Perform iterations
                        try:
                            raw_request = {'method': method, 'url': entry['endpoint'], 'headers': headers}
                            if method == 'POST':


                                if entry['sampleRequestLocation'] != '':

                                    try:
                                        with open(entry['sampleRequestLocation'], 'r') as f:
                                            sample_request_content = f.read()
                                    except FileNotFoundError:
                                        raise ValueError(f"ERROR: Please check the XML/JSON payload file. File not found: {entry['sampleRequestLocation']}")

                                    try:
                                        xml_root = ET.fromstring(sample_request_content)
                                        # Convert XML object to string for display
                                        xml_string = ET.tostring(xml_root, encoding='unicode')
                                        raw_request['data'] = xml_string
                                        raw_request['xml'] = xml_string
                                        raw_request['headers']['Content-Type'] = 'application/xml'

                                    except ET.ParseError:
                                        # If parsing as XML fails, consider it as JSON
                                        try:
                                            json_content = json.loads(sample_request_content)
                                            raw_request['data'] = json_content
                                            raw_request['json'] = json_content
                                            raw_request['headers']['Content-Type'] = 'application/json'
                                        except ValueError:
                                            return jsonify(
                                                {'status': 'error', 'message': 'Invalid sample request content!'})
                            if service_operation_key not in processed_requests:
                                raw_requests.append(raw_request)
                                processed_requests.add(service_operation_key)  # Mark as processed

                            if not request_executed:
                                if method == 'GET':
                                    response = requests.get(entry['endpoint'], headers=headers)
                                else:
                                    # Determine request content type based on sample request location file content
                                    content_type = 'application/json'
                                    if entry['sampleRequestLocation'] != '':
                                        with open(entry['sampleRequestLocation'], 'r') as f:
                                            sample_request_content = f.read()
                                            try:
                                                # Try parsing the content as XML
                                                ET.fromstring(sample_request_content)
                                                content_type = 'application/xml'
                                            except ET.ParseError:
                                                # If parsing as XML fails, consider it as JSON
                                                try:
                                                    json.loads(sample_request_content)
                                                except ValueError:
                                                    return jsonify({'status': 'error', 'message': 'Invalid sample request content!'})

                                    # Send request with appropriate content type
                                    if content_type == 'application/xml':
                                        response = requests.post(entry['endpoint'], headers=headers, data=sample_request_content.encode('utf-8'))
                                    else:
                                        response = requests.post(entry['endpoint'], headers=headers, json=json.loads(sample_request_content))

                                    request_executed = True

                            # Parse response to extract StatusCD and StatusDesc if available
                            status_cd = None
                            status_desc = None
                            try:
                                root = ET.fromstring(response.text)
                                status_cd_element = root.find('.//StatusCD')
                                status_cd = status_cd_element.text if status_cd_element is not None else ''

                                status_desc_element = root.find('.//StatusDesc')
                                status_desc = status_desc_element.text if status_desc_element is not None else ''
                            except (ET.ParseError, AttributeError):
                                try:
                                    json_response = json.loads(response.text)
                                    status_cd = json_response.get('StatusCD', '')
                                    status_desc = json_response.get('StatusDesc', '')
                                except (json.JSONDecodeError, AttributeError):
                                    pass

                            # Perform validation based on successCriteria
                            iteration_status = 'PASS' if entry['successCriteria'] in response.text else 'FAIL'
                            if iteration_status == 'PASS':
                                passed_count += 1  # Increment passed count
                            if overall_status != 'RED' and iteration_status == 'FAIL':
                                overall_status = 'AMBER'  # Update overall_status if any iteration fails
                            if overall_status != 'AMBER' and iteration_status == 'AMBER':
                                overall_status = 'AMBER'  # Update overall_status if any iteration is AMBER
                            if iteration_status == 'FAIL':
                                overall_status = 'RED'  # Update overall_status if any iteration fails

                            responses.append({'response': response.text, 'status': iteration_status, 'status_cd': status_cd, 'status_desc': status_desc})

                            # Append response code and message to status_descriptions
                            if iteration_status == 'FAIL':
                                overall_status = 'AMBER'
                                status_descriptions.append('200 - Business Exception')
                            else:
                                status_descriptions.append(f'{response.status_code} - {response.reason}')

                        except requests.exceptions.ConnectionError as e:
                            overall_status = 'RED';
                            responses.append(
                                {'response': f'Connection error occurred while accessing the service: {str(e)}', 'status': 'ERROR'})
                            status_descriptions.append('500 - Internal Server Error')
                        except RequestException as e:
                            overall_status = 'RED';
                            responses.append(
                                {'response': f'Error occurred while accessing the service: {str(e)}', 'status': 'ERROR'})
                            status_descriptions.append(f'{response.status_code} - {response.reason}')
                    break

            # Now, serialize the raw requests to JSON
            serialized_raw_requests = []
            for requestw in raw_requests:
                print(requestw)
                serialized_request = {
                    'method': requestw['method'],
                    'url': requestw['url'],
                    'headers': requestw['headers']
                }
                # Include data if present and not XML
                if 'data' in requestw:
                    if 'xml' in requestw:
                        serialized_request['data'] = requestw['xml']
                    else:
                        serialized_request['data'] = requestw['data']
                serialized_raw_requests.append(serialized_request)

            # Include serialized raw requests in the result
            result['responses'][service] = {
                'responses': responses,
                'passed_count': passed_count,
                'total_iterations': iteration_count,
                'overall_status': overall_status,
                'status_descriptions': status_descriptions,
                'raw_requests': serialized_raw_requests
            }

        # print(result)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == "__main__":
    app.run(debug=True)
