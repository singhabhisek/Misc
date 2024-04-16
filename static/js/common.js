  var selectedApp = '';
    var targetJson = '';

    $(document).ready(function() {
        var table = $('#service-table').DataTable({
       drawCallback: function(settings) {
           // Hide the last two columns on each page draw
           $(this.api().table().container())
               .find('tbody tr')
               .find('td:nth-last-child(-n+2)')
               .hide();
       },
       autoWidth: false,
       order: [], // Disable initial sorting
       columnDefs: [
           { targets: [0, 3, 4, 6], orderable: false } // Disable sorting for the first column (Select All checkbox)
       ],
       select: true
   });

        // Event handler for "Select All" checkbox
        $('#select-all').change(function() {
            var isChecked = $(this).prop('checked');
            $('#service-table').DataTable().rows().every(function() {
                var rowNode = this.node();
                var checkbox = $(rowNode).find('input[name="service"]');
                checkbox.prop('checked', isChecked);
            });
        });

        // Event handler for individual checkboxes
        $(document).on('change', 'input[name="service"]', function() {
            // Check if all checkboxes are checked
            var allChecked = $('input[name="service"]:checked').length === $('input[name="service"]').length;
            // Update the state of the "Select All" checkbox
            $('#select-all').prop('checked', allChecked);
        });

        // Event handler for the "Select All" checkbox
        $(document).on('change', '#select-all', function() {
            // Update the state of all checkboxes based on the "Select All" checkbox
            $('input[name="service"]').prop('checked', $(this).prop('checked'));
        });

        // Event handler for application select change
        $('#app-dropdown').change(function() {
            // Clear the DataTable
            table.clear().draw();
            // Uncheck the select all checkbox
            $('#select-all').prop('checked', false);
            // Get the selected application name
            selectedApp = $(this).find('option:selected').text();
            $('#passed-count-value').text('');
            $('#failed-at-least-once-count-value').text('');
            $('#failed-all-count-value').text('');
            // Load service details based on selected application
            $.getJSON('/static/config/app_config.json', function(data) {
                targetJson = '';
                // Find the object with the matching application name
                data.applications.forEach(function(app) {
                    if (app.name === selectedApp) {
                        targetJson = app.file; // Set the target JSON file path
                        return false; // Exit the loop once found
                    }
                });
                // Load service details from the target JSON file
                $.getJSON(targetJson, function(serviceData) {
                    // Populate service details in the table
                    $.each(serviceData.entries, function(index, entry) {
                        var overallStatus = entry.overall_status;
                        var passedCount = entry.passed_count;
                        var totalCount = entry.total_iterations;
                        var iterationStatusText = passedCount + ' / ' + totalCount;
                        // Add new row to the table
                        table.row.add([
                            '<input type="checkbox" name="service" value="' + entry.serviceName + ':' + entry.operationName + '">',
                            entry.serviceName,
                            entry.operationName,
                            '', // Placeholder for status icon
                            '', // Placeholder for status description
                            entry.useCase,
                            '<button type="button" style="display:none" class="btn btn-primary show-results-btn">Results</button>',
                            '', // Placeholder for Response info
                            '' //placeholder for Requests
                        ]); // Add new row without redrawing
                    });
                    // Redraw the table
                    table.draw();
                }).fail(function(jqXHR, textStatus, errorThrown) {
                    console.error('Error fetching JSON file:', textStatus, errorThrown);
                });
            });
        });

        // Submit button Logic
        $('#submit-btn').click(function() {
            // Clear the table body
            //$('#service-table tbody').empty();
            // Remove any existing accordion elements
            $('.accordion').empty();
            // Remove any existing accordion elements and modal contents
            $('.accordion').remove();
            $('.modal').remove();
            $('.status-icon').attr('src', ''); // Clear status icons
            $('.status-icon').next('span').remove(); // Remove any existing count
            $('td:nth-child(7)').empty(); // Clear Info column content
            $('td:nth-child(8)').empty(); // Clear Results column content
            $('.status-icon').attr('src', '').removeAttr('title'); // Clear status icons and tooltips
            $('td:nth-child(4)').empty(); // Clear Status column content
            $('td:nth-child(5)').empty(); // Clear Status Description column content
            // Clear previous counts
            $('#passed-count-value').text('');
            $('#failed-at-least-once-count-value').text('');
            $('#failed-all-count-value').text('');
            var selectedServices = [];
            $('#service-table').DataTable().rows().every(function() {
                var rowData = this.data();
                var rowNode = this.node();
                var checkbox = $(rowNode).find('input[type="checkbox"]');
                if (checkbox.prop('checked')) {
                    selectedServices.push(rowData[1] + ':' + rowData[2]); // Concatenate ServiceName and OperationName
                }
            });
            if (selectedServices.length === 0) {
                showConfirmation('Please select at least one service to execute.','error');
                return;
            }
            $('#loader-overlay').show(); // Show the loader overlay
            var iterationCount = $('#iteration-count').val(); // Get the value of iteration count
            var requestData = {
                services: selectedServices,
                targetJson: targetJson,
                iterationCount: iterationCount // Include iteration count in the data
            };
            $.ajax({
                url: '/execute',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify(requestData), // Stringify the request data
                success: function(response) {
                    // Calculate counts based on response
                    var passedCount = 0;
                    var failedAtLeastOnceCount = 0;
                    var failedAllCount = 0;
                    $.each(response.responses, function(serviceName, serviceData) {


                        //count for overall report
                        if (serviceData.overall_status === 'GREEN') {
                            passedCount++;
                        } else if (serviceData.overall_status === 'RED') {
                            failedAllCount++;
                        } else if (serviceData.overall_status === 'AMBER') {
                            failedAtLeastOnceCount++;
                        }
                        //populate all rows with relevant details
                        var serviceNameParts = serviceName.split(':'); // Split serviceName:OperationName into parts
                        if (serviceNameParts.length !== 2) {
                            console.error('Invalid service name format:', serviceName);
                            return; // Skip this service if the format is invalid
                        }
                        var actualServiceName = serviceNameParts[0]; // Extract actual serviceName
                        var actualOperationName = serviceNameParts[1]; // Extract actual OperationName
                        $('#service-table').DataTable().rows().every(function(index) {
                            var rowData = this.data();
                            var rowNode = this.node();
                            if (rowData[1] === actualServiceName && rowData[2] === actualOperationName) {
                                var overallStatusCell = $(rowNode).find('td:nth-child(4)');
                                var statusDescriptionCell = $(rowNode).find('td:nth-child(5)');
                                var infoCell = $(rowNode).find('td:nth-child(7)');
                                var resultCell = $(rowNode).find('td:nth-child(8)');
                                // Update overall status
                                var statusColor = "";
                                if (serviceData.overall_status === "GREEN") {
                                    statusColor = "/static/images/green.png";
                                } else if (serviceData.overall_status === "AMBER") {
                                    statusColor = "/static/images/amber.png";
                                } else if (serviceData.overall_status === "RED") {
                                    statusColor = "/static/images/red.png";
                                }
                                overallStatusCell.html('<img src="' + statusColor + '" alt="' + serviceData.overall_status + '">');
                                overallStatusCell.append($('<span>').text(' ' + serviceData.passed_count + ' of ' + serviceData.total_iterations));
                                var requestExecutedCell = $(rowNode).find('td:nth-child(9)');
<!--                                // Update the hidden column with raw requests data-->
<!--                                 var rawRequests = '';-->
<!--                                    serviceData.raw_requests.forEach(function(request) {-->
<!--                                        rawRequests += request.method + ' ' + request.url + '<br/>';-->
<!--                                        // Include headers-->
<!--                                        rawRequests += 'Headers: ' + JSON.stringify(request.headers) + '<br/>';-->
<!--                                        // Include request body for POST calls-->
<!--                                        if (request.method === 'POST' && request.body) {-->
<!--                                            rawRequests += 'Request Body: ' + JSON.stringify(request.body) ;-->
<!--                                        }-->
<!--                                    });-->

<!--                                requestExecutedCell.html(rawRequests);-->
                                    // Update the hidden column with raw requests data
                                    var rawRequests = '';
                                    serviceData.raw_requests.forEach(function(request) {
                                        rawRequests += request.method + ' ' + request.url + '\n';
                                        // Include headers
                                        rawRequests += 'Headers: ' + JSON.stringify(request.headers) + '\n';
                                        // Include request body for POST calls
                                        if (request.method === 'POST' && request.data) {
                                            if (request.headers['Content-Type'] === 'application/xml') {
                                                rawRequests += 'Request Body (XML): ' + request.data ;
                                            } else if (request.headers['Content-Type'] === 'application/json') {
                                                rawRequests += 'Request Body (JSON): ' + JSON.stringify(request.data) ;
                                            }
                                        }
                                    });
                                    console.log(rawRequests);
                                    requestExecutedCell.html(rawRequests);
                                requestExecutedCell.hide(); // Hide the cell
                                // Update status description
                                statusDescriptionCell.empty();
                                $.each(serviceData.status_descriptions, function(index, description) {
                                    statusDescriptionCell.append('<div>Iteration ' + (index + 1) + ': ' + description + '</div>');
                                });
                                // Update "Show Results" button
                                infoCell.html('<button type="button" class="btn btn-info show-results-btn" data-toggle="modal" data-target="#modal-' + actualServiceName + '">Results</button>');
                                // Update result cell
                                resultCell.empty();
                                $.each(serviceData.responses, function(index, iterationResponse) {
                                    var iterationNumber = index + 1;
                                    var iterationStatus = iterationResponse.status === 'PASS' ? 'PASS' : 'FAIL';
                                    // Replace newline characters with HTML line breaks
                                    var responseContent = iterationResponse.response; //.replace(/\n/g, '<br>');
                                     resultCell.append('\n<div>Iteration ' + iterationNumber + ' - ' + iterationStatus + '\n</div><div>' + responseContent + '</div>');
                                 });
                                var accordionContainer = $('<div class="accordion" id="accordion-' + actualServiceName + '">');
                                $.each(serviceData.responses, function(index, iterationResponse) {
                                    var iterationNumber = index + 1;
                                    var iterationStatus = iterationResponse.status === 'PASS' ? 'PASS' : 'FAIL';
                                    accordionContainer.append(
                                        '<div class="card">' +
                                        '<div class="card-header">' +
                                        '<h2 class="mb-0">' +
                                        '<button class="btn btn-link" type="button" data-toggle="collapse" ' +
                                        'data-target="#collapse-' + actualServiceName + '-' + iterationNumber + '">' +
                                        'Iteration ' + iterationNumber + ' - ' + iterationStatus +
                                        '</button>' +
                                        '</h2>' +
                                        '</div>' +
                                        '<div id="collapse-' + actualServiceName + '-' + iterationNumber + '" class="collapse" ' +
                                        'aria-labelledby="heading-' + actualServiceName + '-' + iterationNumber + '" ' +
                                        'data-parent="#accordion-' + actualServiceName + '">' +
                                        '<div class="card-body">' +
                                        iterationResponse.response +
                                        '</div>' +
                                        '</div>' +
                                        '</div>'
                                    );
                                });
                                var modalContent = $('<div class="modal fade" id="modal-' + actualServiceName + '">').append(
                                    $('<div class="modal-dialog modal-dialog-scrollable modal-lg">').append(
                                        $('<div class="modal-content">').append(
                                            $('<div class="modal-header">').append(
                                                $('<h5 class="modal-title">').text('Results for ' + actualServiceName + ':' + actualOperationName)
                                            ),
                                            $('<div class="modal-body">').append(accordionContainer),
                                            $('<div class="modal-footer">').append(
                                                $('<button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>')
                                            )
                                        )
                                    )
                                );
                                $('body').append(modalContent);
                            }
                        });
                    });
                    $('#loader-overlay').hide(); // Hide the loader overlay on success
                    // Update count placeholders
                    $('#passed-count-value').text(passedCount);
                    $('#failed-at-least-once-count-value').text(failedAtLeastOnceCount);
                    $('#failed-all-count-value').text(failedAllCount);
                    // Show success message using SweetAlert
<!--                    Swal.fire({-->
<!--                        icon: 'success',-->
<!--                        title: 'Execution completed!',-->
<!--                        showConfirmButton: false,-->
<!--                        timer: 1500 // Automatically close after 1.5 seconds-->
<!--                    });-->


                   showConfirmation('Execution Completed', 'success');

                },
                error: function(xhr, status, error) {
                    $('#loader-overlay').hide(); // Hide the loader overlay on error
                    // Show error message using SweetAlert
<!--                    Swal.fire({-->
<!--                        icon: 'error',-->
<!--                        title: 'Error!',-->
<!--                        text: 'Error: ' + xhr.responseText-->
<!--                    });-->
                   showConfirmation('An error occurred. Please try again.', 'error');

                }
            });
            // Hide the last column ("Result")
            $('#service-table td:nth-last-child(1)').hide(); // Hide the second-to-last column
            // table.column(-1).visible(false);
        });

        //reset button logic
        $('#reset-btn').click(function() {
            $('input[name="service"]').prop('checked', false); // Uncheck all checkboxes
            // Reset select all checkbox
            document.getElementById("select-all").checked = false;
            $('.status-icon').attr('src', '').removeAttr('title'); // Clear status icons and tooltips
            $('#service-table').DataTable().rows().every(function() {
                var rowNode = this.node();
                $(rowNode).find('td:nth-child(4)').empty(); // Clear Status column content
                $(rowNode).find('td:nth-child(5)').empty(); // Clear Status Description column content
                $(rowNode).find('td:nth-child(7)').empty(); // Clear Info column content
                $(rowNode).find('td:nth-child(8)').empty(); // Clear Results column content
                var checkbox = $(rowNode).find('input[type="checkbox"]');
                checkbox.prop('checked', false);
            });
        });
    });

    function showAlert(message) {
        $('#alert-message').text(message);
        $('#custom-alert').modal('show');
    }

