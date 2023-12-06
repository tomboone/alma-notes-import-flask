import csv
import requests
import json
from settings import ALMA_SERVER, ALMA_API_KEY


def batch(csvfile, almafield):
    with open(csvfile) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        rownumber = 1

        # Iterate through each row of the CSV
        for row in csv_reader:
            barcode = row[0]  # Column 1 = barcode
            note = row[1]  # Column 2 = value to insert as a note

            # Get item record from barcode via requests
            try:
                r = requests.get(ALMA_SERVER + '/almaws/v1/items', params={
                    'apikey': ALMA_API_KEY,
                    'item_barcode': barcode,
                    'format': 'json'
                })

                # Provide for reporting HTTP errors
                r.raise_for_status()

            except requests.exceptions.HTTPError as errh:

                # If HTTP error, inform user
                print('HTTP Error finding Barcode ' + str(barcode) + ' in row ' + str(rownumber) + ':', errh)

                # Bump the row number up before exiting
                rownumber = rownumber + 1

                # Stop processing this row
                continue

            except requests.exceptions.ConnectionError as errc:

                # If connection error, inform user
                print('Connection Error finding Barcode ' + str(barcode) + ' in row ' + str(rownumber) + ':', errc)

                # Bump the row number up before exiting
                rownumber = rownumber + 1

                # Stop processing this row
                continue

            except requests.exceptions.Timeout as errt:

                # If timeout error, inform user
                print('Timeout Error finding Barcode ' + str(barcode) + ' in row ' + str(rownumber) + ':', errt)

                # Bump the row number up before exiting
                rownumber = rownumber + 1

                # Stop processing this row
                continue

            except requests.exceptions.RequestException as err:

                # If other error, inform user
                print('Other Error finding Barcode ' + str(barcode) + ' in row ' + str(rownumber) + ':', err)

                # Bump the row number up before exiting
                rownumber = rownumber + 1

                # Stop processing this row
                continue

            # If request good, parse JSON into a variable
            itemrec = r.json()

            # Insert column 2 value into the destination field
            itemrec['item_data'][almafield] = note

            # Specify JSON content type for PUT request
            headers = {'content-type': 'application/json'}

            # Get IDs from item record for building PUT request endpoint
            mms_id = itemrec['bib_data']['mms_id']  # Bib ID
            holding_id = itemrec['holding_data']['holding_id']  # Holding ID
            item_pid = itemrec['item_data']['pid']  # Item ID

            # Construct API endpoint for PUT request from item record data
            putendpoint = '/almaws/v1/bibs/' + mms_id + '/holdings/' + holding_id + '/items/' + item_pid

            # send full updated JSON item record via PUT request
            try:
                r = requests.put(ALMA_SERVER + putendpoint, params={
                    'apikey': ALMA_API_KEY
                }, data=json.dumps(itemrec), headers=headers)

                # Provide for reporting HTTP errors
                r.raise_for_status()

            except requests.exceptions.HTTPError as errh:

                # If HTTP error, inform user
                print('HTTP Error updating Barcode ' + str(barcode) + ' in row ' + str(rownumber) + ':', errh)

                # Bump the row number up before exiting
                rownumber = rownumber + 1

                # Stop processing this row
                continue

            except requests.exceptions.ConnectionError as errc:

                # If connection error, inform user
                print('Connection Error updating Barcode ' + str(barcode) + ' in row ' + str(rownumber) + ':', errc)

                # Bump the row number up before exiting
                rownumber = rownumber + 1

                # Stop processing this row
                continue

            except requests.exceptions.Timeout as errt:

                # If timeout error, inform user
                print('Timeout Error updating Barcode ' + str(barcode) + ' in row ' + str(rownumber) + ':', errt)

                # Bump the row number up before exiting
                rownumber = rownumber + 1

                # Stop processing this row
                continue

            except requests.exceptions.RequestException as err:

                # If other error, inform user
                print('Other Error updating Barcode ' + str(barcode) + ' in row ' + str(rownumber) + ':', err)

                # Bump the row number up before exiting
                rownumber = rownumber + 1

                # Stop processing this row
                continue

            # Bump the row number up before going to next row
            rownumber = rownumber + 1

    # Provide import info as output to command line
    print('Import complete. All submitted barcodes (except any errors listed above) have been updated in Alma.')
