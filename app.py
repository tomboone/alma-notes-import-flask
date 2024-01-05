from flask import Flask, render_template, flash, session, redirect, url_for, request, abort
from celery import Celery
from forms import UploadForm, InstitutionForm, UserForm
from werkzeug.utils import secure_filename
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import csv
import chardet
import requests
import json
from settings import ALMA_SERVER, log_dir, SECRET_APP_KEY, sender_email, smtp_address, saml_sp, \
    cookie_issuing_file, institution_code, site_url, shared_secret, database
import smtplib
import email.message
from functools import wraps
import jwt
from models import user_login, db, add_batch_import, check_user, get_batch_imports, get_institutions, addinstitution, \
    get_single_institution, Institution, get_users, User

app = Flask(__name__)

# set up logging to work with WSGI server
if __name__ != '__main__':  # if running under WSGI
    gunicorn_logger = logging.getLogger('gunicorn.error')  # get the gunicorn logger
    app.logger.handlers = gunicorn_logger.handlers  # set the app logger handlers to the gunicorn logger handlers
    app.logger.setLevel(gunicorn_logger.level)  # set the app logger level to the gunicorn logger level

# app configuration
app.config['SECRET_KEY'] = SECRET_APP_KEY
app.config['SHARED_SECRET'] = shared_secret
app.config['SQLALCHEMY_DATABASE_URI'] = database  # set the database URI
app.config['UPLOAD_FOLDER'] = 'static/csv'

db.init_app(app)  # initialize SQLAlchemy

# database
with app.app_context():  # need to be in app context to create the database
    db.create_all()  # create the database


# Celery configuration
app.config['broker_url'] = 'redis://127.0.0.1:6379'
app.config['result_backend'] = 'db+' + database

# Initialize Celery
celery = Celery(app.name, broker=app.config['broker_url'])
celery.conf.update(app.config)


# set up error handlers & templates for HTTP codes used in abort()
#   see http://flask.pocoo.org/docs/1.0/patterns/errorpages/
# 400 error handler
@app.errorhandler(400)
def badrequest(e):
    return render_template('error_400.html', e=e), 400  # render the error template


# 403 error handler
@app.errorhandler(403)
def forbidden(e):
    return render_template('unauthorized.html', e=e), 403  # render the error template


# 500 error handler
@app.errorhandler(500)
def internalerror(e):
    return render_template('error_500.html', e=e), 500  # render the error template


# app log
logdir = log_dir  # set the log directory
log_file = logdir + '/app.log'  # set the log file
app_log = logging.getLogger('app')  # create the batch log
app_log.setLevel(logging.INFO)  # set the batch log level
file_handler = TimedRotatingFileHandler(log_file, when='midnight')  # create a file handler
file_handler.setLevel(logging.INFO)  # set the file handler level
file_handler.setFormatter(  # set the file handler format
    logging.Formatter(
        '%(asctime)s %(levelname)-8s %(message)s', datefmt='%m/%d/%Y %H:%M:%S'
    ))
app_log.addHandler(file_handler)  # add the file handler to the batch log


# decorator for pages that need auth
def auth_required(f):
    @wraps(f)  # preserve the original function's metadata
    def decorated(*args, **kwargs):  # the wrapper function
        if 'username' not in session:  # if the user is not logged in
            return redirect(url_for('login'))  # redirect to the login page
        else:
            return f(*args, **kwargs)  # otherwise, call the original function

    return decorated


##########
# Routes #
##########

@app.route('/', methods=['GET', 'POST'])
@auth_required
def upload():
    if 'almanotesimport' not in session['authorizations']:
        abort(403)
    form = UploadForm()
    izs = get_institutions()  # Get the institutions from the database
    form.iz.choices = [(i.code, i.name) for i in izs]  # Set the choices for the institution field
    if form.validate_on_submit():
        # File
        file = form.csv.data  # Get the CSV file from the form
        filename = secure_filename(file.filename)  # Get the filename from the file

        # If the filename already exists in the upload folder...
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
            name, ext = os.path.splitext(file.filename)  # ...get the filename and extension
            count = 0  # ...initialize filecount
            # ...while the filename and filecount exists...
            while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], name) + '-{}'.format(count) + ext):
                count += 1  # ...increment the filecount until the filename doesn't exist
            filename = name + '-{}'.format(count) + ext  # ...add the new filecount to the filename

        secfilename = secure_filename(filename)  # Make the filename safe, even though it should be safe already

        # Save the file to the CSV folder in the instance path
        file.save(os.path.join(
            app.config['UPLOAD_FOLDER'], secfilename
        ))

        # Field
        field = form.almafield.data  # Get the Alma field from the form

        iz = form.iz.data  # Get the institution from the form
        apikey = get_single_institution(iz).apikey  # Get the API key for the institution

        user = check_user(session['username'])  # Get the current user object

        # Run the batch function on the CSV file
        task = batch.delay(
            os.path.join(
                app.config['UPLOAD_FOLDER'], secfilename
            ), field, user.emailaddress, apikey
        )

        # Add task to database
        add_batch_import(task.id, filename, field, user.id, iz)

        # Provide import info as message to user
        flash(
            'The CSV "' + filename + '" is being processed (taskid = ' + str(
                task.id) + '). An email will be sent to {} when complete.'.format(session['email']),
            'info'
        )
        return redirect(url_for('upload'))

    # Get batch imports from database
    batch_imports = get_batch_imports()  # Get the batch imports from the database
    imports = []  # Initialize the imports list
    for batch_import in batch_imports:  # Iterate through the batch imports
        app_log.debug(celery.AsyncResult(batch_import.uuid).result)  # Log the result of the task
        status = celery.AsyncResult(batch_import.uuid).status  # Get the status of the task
        result = celery.AsyncResult(batch_import.uuid).result  # Get the result of the task
        imports.append({  # Add the batch import to the imports list with the status and result
            'filename': batch_import.filename,
            'field': batch_import.field,
            'date': batch_import.date,
            'user': batch_import.displayname,
            'institution': batch_import.name,
            'status': status,
            'result': result
        })
    return render_template('upload.html', form=form, imports=imports, uploadfolder=app.config['UPLOAD_FOLDER'])


@app.route('/login')
def login():
    if 'username' in session:
        return redirect(url_for('upload'))
    else:
        login_url = saml_sp
        login_url += cookie_issuing_file
        login_url += '?institution='
        login_url += institution_code
        login_url += '&url='
        login_url += site_url
        login_url += '/login/n'
        return render_template('login.html', login_url=login_url)


@app.route('/login/n')
def new_login():
    session.clear()
    if 'wrt' in request.cookies:  # if the login cookie is present
        encoded_token = request.cookies['wrt']  # get the login cookie
        user_data = jwt.decode(encoded_token, app.config['SHARED_SECRET'], algorithms=['HS256'])  # decode the token
        user_login(session, user_data)  # Log the user in

        if 'almanotesimport' in session['authorizations']:  # if the user is an exceptions user
            return redirect(url_for('upload'))  # redirect to the home page
        else:
            abort(403)  # otherwise, abort with a 403 error
    else:
        return "no login cookie"  # if the login cookie is not present, return an error


# Logout handler
@app.route('/logout')
@auth_required
def logout():
    session.clear()  # clear the session
    return redirect(url_for('upload'))  # redirect to the home page


# Institutions handler
@app.route('/institutions')
@auth_required
def institutions():
    if 'admin' not in session['authorizations']:
        abort(403)
    izs = get_institutions()
    return render_template('institutions.html', izs=izs)


# Institution handler
@app.route('/institutions/<code>')
@auth_required
def edit_institution(code):
    if 'admin' not in session['authorizations']:
        abort(403)
    iz = Institution.query.get_or_404(code)
    form = InstitutionForm(obj=iz)
    if form.validate_on_submit():
        iz.name = form.name.data
        iz.code = form.code.data
        db.session.commit()
        flash(iz.name + ' updated', 'info')
        return redirect(url_for('institutions'))
    return render_template('edit_institution.html', form=form)


# Add institution handler
@app.route('/institutions/add', methods=['GET', 'POST'])
@auth_required
def add_institution():
    if 'admin' not in session['authorizations']:
        abort(403)
    form = InstitutionForm()
    if form.validate_on_submit():
        name = form.name.data
        code = form.code.data
        apikey = form.apikey.data
        addinstitution(code, name, apikey)
        flash('Institution added', 'info')
        return redirect(url_for('institutions'))
    return render_template('add_institution.html', form=form)


# Users handler
@app.route('/users')
@auth_required
def users():
    if 'admin' not in session['authorizations']:
        abort(403)
    allusers = get_users()
    return render_template('users.html', allusers=allusers)


# Edit User handler
@app.route('/users/<userid>', methods=['GET', 'POST'])
@auth_required
def edit_user(userid):
    if 'admin' not in session['authorizations']:
        abort(403)
    edituser = User.query.get_or_404(userid)
    form = UserForm(obj=edituser)
    if form.validate_on_submit():
        edituser.username = form.username.data
        edituser.displayname = form.displayname.data
        edituser.emailaddress = form.email.data
        edituser.admin = form.admin.data
        db.session.commit()
        flash(edituser.displayname + ' updated', 'info')
        return redirect(url_for('users'))
    return render_template('edit_user.html', form=form)


################
# Celery tasks #
################

# Celery task
@celery.task
def batch(csvfile, almafield, useremail, key):
    filename = csvfile.replace('static/csv', '')  # Set filename for email log
    emailbody = 'Results for {}:\n'.format(filename)  # Initialize email body
    app_log.info('Processing CSV file: ' + filename)  # Log info

    with open(csvfile) as csv_file:  # Open CSV file
        encoding = chardet.detect(csv_file.read().encode())['encoding']  # Detect encoding

    with open(csvfile, encoding=encoding) as csv_file:  # Open CSV file
        csv_reader = csv.reader(csv_file, delimiter=',')  # Open CSV file for reading
        rownumber = 1  # Initialize row number for email log
        failed = 0  # Initialize failed row counter for email log
        success = 0  # Initialize success row counter for email log

        for row in csv_reader:  # Iterate through each row of the CSV file
            barcode = row[0]  # Column 1 = barcode
            note = row[1]  # Column 2 = value to insert as a note
            app_log.debug('Processing row ' + str(rownumber) + ': barcode ' + str(barcode) + '; value ' + str(note))

            try:  # Get item record from barcode via requests
                r = requests.get(ALMA_SERVER + '/almaws/v1/items', params={
                    'apikey': key,
                    'item_barcode': barcode,
                    'format': 'json'
                })
                r.raise_for_status()  # Provide for reporting HTTP errors

            except Exception as errh:  # If error...
                emailbody += 'Error finding Barcode ' + str(barcode) + ' in row ' + \
                             str(rownumber) + ': {}\n'.format(errh)
                app_log.error('Error finding Barcode ' + str(barcode) + ' in row ' +
                              str(rownumber) + ': {}'.format(errh))
                rownumber = rownumber + 1  # Bump the row number up before exiting
                failed = failed + 1
                continue  # Stop processing this row

            itemrec = r.json()  # If request good, parse JSON into a variable
            itemrec['item_data'][almafield] = note  # Insert column 2 value into the destination field
            headers = {'content-type': 'application/json'}  # Specify JSON content type for PUT request

            # Get IDs from item record for building PUT request endpoint
            mms_id = itemrec['bib_data']['mms_id']  # Bib ID
            holding_id = itemrec['holding_data']['holding_id']  # Holding ID
            item_pid = itemrec['item_data']['pid']  # Item ID

            # Construct API endpoint for PUT request from item record data
            putendpoint = '/almaws/v1/bibs/' + mms_id + '/holdings/' + holding_id + '/items/' + item_pid

            try:  # send full updated JSON item record via PUT request
                r = requests.put(ALMA_SERVER + putendpoint, params={
                    'apikey': key
                }, data=json.dumps(itemrec), headers=headers)
                r.raise_for_status()  # Provide for reporting HTTP errors

            except Exception as errh:  # If error...
                emailbody += 'Error updating Barcode ' + str(barcode) + ' in row ' + \
                             str(rownumber) + ': {}\n'.format(errh)
                app_log.error('Error updating Barcode ' + str(barcode) + ' in row ' +
                              str(rownumber) + ': {}'.format(errh))
                rownumber = rownumber + 1  # Bump the row number up before exiting
                failed = failed + 1
                continue  # Stop processing this row

            rownumber = rownumber + 1  # Bump the row number up before going to next row
            success = success + 1
            app_log.debug('Barcode ' + str(barcode) + ' updated in row ' + str(rownumber) + '.')

    # Provide import info as output to command line
    emailbody += str(success) + ' barcodes updated.\n'
    emailbody += str(failed) + ' barcodes not updated.'
    if failed > 0:
        emailbody += ' (See errors above.)'
    app_log.info('Import complete. ' + str(success) + ' barcodes updated. ' + str(failed) + ' barcodes not updated.')

    # Send email to user
    send_email(emailbody, filename, useremail)

    return emailbody  # Return email body for testing


####################
# Helper functions #
####################

# Send email
def send_email(body, filename, useremail):
    message = email.message.Message()  # create message
    message["Subject"] = 'Results for {}'.format(filename)  # set subject
    message["From"] = sender_email  # set sender
    message["To"] = useremail  # set recipient
    message.add_header('Content-Type', 'text')  # set content type
    message.set_payload(body)  # set body

    try:  # try to send email
        smtp = smtplib.SMTP(smtp_address)  # create smtp server
        smtp.sendmail(message['From'], message['To'], message.as_string())  # send email
        smtp.quit()  # quit smtp server
    except Exception as e:  # catch exception
        app_log.error('Error sending email to {}: '.format(useremail) + '{}'.format(e))  # log error
    else:  # if no exception
        app_log.info('Email sent to {}'.format(useremail))  # log info


if __name__ == '__main__':
    app.run()
