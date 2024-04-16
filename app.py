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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_json(data):
    required_keys = ['serviceName', 'operationName', 'useCase', 'successCriteria', 'endpoint', 'headers']
    for entry in data['entries']:
        for key in required_keys:
            if key not in entry:
                return False
    return True

def backup_config():
    original_path = os.path.join(UPLOAD_FOLDER, 'config.json')
    timestamp = datetime.now().strftime("%Y%m%d")
    backup_path = os.path.join(UPLOAD_FOLDER, f'config_backup_{timestamp}.json')
    try:
        os.rename(original_path, backup_path)
        return True
    except Exception as e:
        print(f"Error while creating backup: {e}")
        return False


@app.route('/upload',  methods=['GET', 'POST'])
def upload():
    if request.method == 'GET':
        return render_template('upload_config.html')

    else:
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': ' No config file was provided '}), 500
            # return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            try:
                data = json.loads(file.read())
            except json.JSONDecodeError as e:
                return jsonify({'status': 'error', 'message': 'Invalid JSON format'}), 500
            if validate_json(data):
                backup_successful = backup_config()
                if not backup_successful:
                    return jsonify({'status': 'error', 'message': 'Error creating backup'}), 500
                filename = 'config.json'
                file.seek(0)  # Reset file pointer to start before saving
                file.save(os.path.join(UPLOAD_FOLDER, filename))

                return jsonify({'status': 'success', 'message': 'File uploaded successfully'}), 200
            else:
                return jsonify({'status': 'error',
                                'message': 'Invalid JSON structure. Missing one or more required keys in "entries".'}), 500
        else:
            return jsonify({'status': 'error', 'message': 'Invalid file format. Only JSON files are allowed.'}), 500
    return render_template('upload_config.html')



@app.route('/execute', methods=['POST'])
def execute():
    """
    Execute the selected services based on the provided JSON configuration.
    """
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
                                with open(entry['sampleRequestLocation'], 'r') as f:
                                    sample_request_content = f.read()
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

                        responses.append({'response': response.text, 'status': iteration_status})

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

if __name__ == "__main__":
    app.run(debug=True)
