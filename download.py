"""
This script was inspired from tmcw's Ruby script doing the same thing:

    https://gist.github.com/tmcw/1098861

And recent fixes implemented thanks to the login structure by wederbrand:

    https://github.com/wederbrand/workout-exchange/blob/master/garmin_connect/download_all.rb

The goal is to iteratively download all detailed information from Garmin Connect
and store it locally for further perusal and analysis. This is still very much
preliminary; future versions should include the ability to seamlessly merge
all the data into a single file, filter by workout type, and other features
to be determined.
"""

import argparse
from getpass import getpass
import json
import mechanize as me
import os
import re
import shutil
import sys
import urllib

BASE_URL = "http://connect.garmin.com/en-US/signin"
GAUTH = "http://connect.garmin.com/gauth/hostname"
SSO = "https://sso.garmin.com/sso"
CSS = "https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.1-min.css"
REDIRECT = "https://connect.garmin.com/post-auth/login"
ACTIVITIES = "http://connect.garmin.com/proxy/activity-search-service-1.2/json/activities?start=%s&limit=%s"
FIT = "https://connect.garmin.com/proxy/download-service/files/activity/%s"
TCX = "https://connect.garmin.com/proxy/activity-service-1.1/tcx/activity/%s?full=true"
GPX = "https://connect.garmin.com/proxy/activity-service-1.1/gpx/activity/%s?full=true"
KML = "https://connect.garmin.com/proxy/activity-service-1.0/kml/activity/%s?full=true"

def login(agent, username, password):
    global BASE_URL, GAUTH, REDIRECT, SSO, CSS

    # First establish contact with Garmin and decipher the local host.
    page = agent.open(BASE_URL)
    pattern = "\"\S+sso\.garmin\.com\S+\""
    script_url = re.search(pattern, page.get_data()).group()[1:-1]
    agent.set_handle_robots(False)   # no robots
    agent.set_handle_refresh(False)  # can sometimes hang without this
    agent.open(script_url)
    hostname_url = agent.open(GAUTH)
    hostname = json.loads(hostname_url.get_data())['host']

    # Package the full login GET request...
    data = {'service': REDIRECT,
        'webhost': hostname,
        'source': BASE_URL,
        'redirectAfterAccountLoginUrl': REDIRECT,
        'redirectAfterAccountCreationUrl': REDIRECT,
        'gauthHost': SSO,
        'locale': 'en_US',
        'id': 'gauth-widget',
        'cssUrl': CSS,
        'clientId': 'GarminConnect',
        'rememberMeShown': 'true',
        'rememberMeChecked': 'false',
        'createAccountShown': 'true',
        'openCreateAccount': 'false',
        'usernameShown': 'false',
        'displayNameShown': 'false',
        'consumeServiceTicket': 'false',
        'initialFocus': 'true',
        'embedWidget': 'false',
        'generateExtraServiceTicket': 'false'}

    # ...and officially say "hello" to Garmin Connect.
    login_url = 'https://sso.garmin.com/sso/login?%s' % urllib.urlencode(data)
    agent.open(login_url)

    # Set up the login form.
    agent.select_form(predicate = lambda f: 'id' in f.attrs and f.attrs['id'] == 'login-form')
    agent['username'] = username
    agent['password'] = password
    agent.addheaders = [('User-agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/535.2 (KHTML, like Gecko) Chrome/15.0.874.121 Safari/535.2'), ]
    agent.set_handle_robots(False)   # no robots
    agent.set_handle_refresh(False)  # can sometimes hang without this
    # Apparently Garmin Connect attempts to filter on these browser headers;
    # without them, the login will fail.

    # Submit the login!
    res = agent.submit()
    if res.get_data().find("Invalid") >= 0:
        quit("Login failed! Check your credentials, or submit a bug report.")
    elif res.get_data().find("SUCCESS") >= 0:
        print 'Login successful! Proceeding...'
    else:
        quit('UNKNOWN STATE. This script may need to be updated. Submit a bug report.')

    # Now we need a very specific URL from the respose.
    response_url = re.search("response_url\s*=\s*'(.*)';", res.get_data()).groups()[0]
    agent.open(response_url)

    # In theory, we're in.

def file_exists_in_folder(filename, folder):
    "Check if the file exists in folder of any subfolder"
    for _, _, files in os.walk(folder):
        if filename in files:
            return True
    return False

def activities(agent, outdir, increment = 100):
    global ACTIVITIES
    currentIndex = 0
    initUrl = ACTIVITIES % (currentIndex, increment)  # 100 activities seems a nice round number
    try:
        response = agent.open(initUrl)
    except:
        print('Wrong credentials for user {}. Skipping.'.format(username))
        return
    search = json.loads(response.get_data())
    totalActivities = int(search['results']['totalFound'])
    while True:
        for item in search['results']['activities']:
            # Read this list of activities and save the files.
            # print '.'
            activityId = item['activity']['activityId']
            activityDate = item['activity']['activitySummary']['BeginTimestamp']['value'][:10]
            url = FIT % activityId
            file_name = '{}_{}.zip'.format(activityDate, activityId)
            if file_exists_in_folder(file_name, output):
                print('{} already exists in {}. Skipping.'.format(file_name, output))
                continue
            print('{} is downloading...'.format(file_name))
            datafile = agent.open(url).get_data()
            file_path = os.path.join(outdir, file_name)
            f = open(file_path, "w")
            f.write(datafile)
            f.close()
            shutil.copy(file_path, os.path.join(os.path.dirname(os.path.dirname(file_path)), file_name))

        if (currentIndex + increment) > totalActivities:
            # All done!
            break

        # We still have at least 1 activity.
        currentIndex += increment
        url = ACTIVITIES % (currentIndex, increment)
        response = agent.open(url)
        search = json.loads(response.get_data())

def download_files_for_user(username, password, output):
    # Create the agent and log in.
    agent = me.Browser()
    login(agent, username, password)

    user_output = os.path.join(output, username)
    download_folder = os.path.join(user_output, 'Historical')

    # Create output directory (if it does not already exist).
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    # Scrape all the activities.
    activities(agent, download_folder)

folder_execute = os.path.dirname(sys.executable)
if folder_execute.endswith('/Contents/MacOS'):
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(folder_execute))))

parser = argparse.ArgumentParser(description = 'Garmin Data Scraper',
    epilog = 'Because the hell with APIs!', add_help = 'How to use',
    prog = 'python download.py -u <user> -c <csv fife with credentials> -o <output dir>')
parser.add_argument('-u', '--user', required = False,
    help = 'Garmin username. This will NOT be saved!')
parser.add_argument('-c', '--csv', required=False,
    help = 'CSV file with username and password (comma separated).',
    default = os.path.join(os.getcwd(), 'credentials.csv'))
parser.add_argument('-o', '--output', required = False,
    help = 'Output directory.', default=os.path.join(os.getcwd(), 'Results/'))

args = vars(parser.parse_args())
# Try to use the user argument from command line
output = args['output']

if args['user'] is not None:
    password = getpass('Garmin account password (NOT saved): ')
    username = args['user']
    download_files_for_user(username, password, output)

# Try to use csv argument from command line

if args['csv'] is not None:
    csv_file_path = args['csv']
    if not os.path.exists(csv_file_path):
        print("CSV file doesn't exist")
        sys.exit()
    else:
        with open(csv_file_path, 'r') as f:
            for line in f:
                try:
                    if ',' in line:
                        username, password = (line.strip().split(','))
                        print 'Downloading files for user {}'.format(username)
                        download_files_for_user(username, password, output)
                except IndexError:
                    raise Exception('Wrong line in CSV file. Please check the line {}'.format(line))

