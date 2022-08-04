import httplib2
import os
import random
import time
import sys
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow
from PyQt5.QtWidgets import QFileDialog, QMainWindow, QApplication, QMessageBox
from PyQt5.uic import loadUi
from PyQt5 import QtWidgets

#YOUTUBE VALID VIDEO FORMATS
YOUTUBE_FORMATS = ('.MOV',
'.MPEG-1',
'.MPEG-2',
'.MPEG4',
'.MP4',
'.MPG',
'.AVI',
'.WMV',
'.MPEGPS',
'.FLV',
'.3GPP',
'.WebM',
'.DNxHR',
'.ProRes',
'.CineForm',
'.HEVC')

# Explicitly tell the underlying HTTP transport library not to retry, since
# we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the Google API Console at
# https://console.developers.google.com/.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = "client_secrets.json"

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the API Console
https://console.developers.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                   CLIENT_SECRETS_FILE))



def get_authenticated_service(args):
  flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
    scope=YOUTUBE_UPLOAD_SCOPE)

  storage = Storage("%s-oauth2.json" % sys.argv[0])
  credentials = storage.get()

  if not credentials or credentials.invalid:
    credentials = run_flow(flow, storage, args)

  return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
    http=credentials.authorize(httplib2.Http()))

def initialize_upload(youtube, options):
  tags = None
  if options.keywords:
    tags = options.keywords.split(",")

  body=dict(
    snippet=dict(
      title=options.video_name,
      description=options.video_desc,
      tags=tags,
      categoryId=options.category
    ),
    status=dict(
      privacyStatus=options.video_privacy
    )
  )

  # Call the API's videos.insert method to create and upload the video.
  insert_request = youtube.videos().insert(
    part=",".join(body.keys()),
    body=body,
    # The chunksize parameter specifies the size of each chunk of data, in
    # bytes, that will be uploaded at a time. Set a higher value for
    # reliable connections as fewer chunks lead to faster uploads. Set a lower
    # value for better recovery on less reliable connections.
    #
    # Setting "chunksize" equal to -1 in the code below means that the entire
    # file will be uploaded in a single HTTP request. (If the upload fails,
    # it will still be retried where it left off.) This is usually a best
    # practice, but if you're using Python older than 2.6 or if you're
    # running on App Engine, you should set the chunksize to something like
    # 1024 * 1024 (1 megabyte).
    media_body=MediaFileUpload(options.video_file_path, chunksize=-1, resumable=True)
  )

  resumable_upload(insert_request)

# This method implements an exponential backoff strategy to resume a
# failed upload.
def resumable_upload(insert_request):
  response = None
  error = None
  retry = 0
  while response is None:
    try:
      print("Uploading file...")
      status, response = insert_request.next_chunk()
      if response is not None:
        if 'id' in response:
          print("Video id '%s' was successfully uploaded." % response['id'])
        else:
          exit("The upload failed with an unexpected response: %s" % response)
    except HttpError as e:
      if e.resp.status in RETRIABLE_STATUS_CODES:
        error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status,
                                                             e.content)
      else:
        raise
    except RETRIABLE_EXCEPTIONS as e:
      error = "A retriable error occurred: %s" % e

    if error is not None:
      print(error)
      retry += 1
      if retry > MAX_RETRIES:
        exit("No longer attempting to retry.")

      max_sleep = 2 ** retry
      sleep_seconds = random.random() * max_sleep
      print("Sleeping %f seconds and then retrying..." % sleep_seconds)
      time.sleep(sleep_seconds)

class Main(QMainWindow):
  video_file_path = ""
  video_name = ""
  description = "test"
  category = "22"
  keywords = "test"
  video_privacy = "private"

  """basic ui for selecting file and submitting youtube video"""
  
  def __init__(self):
    super(Main, self).__init__()
    loadUi("gui.ui", self)
    self.setWindowTitle("Youtube Uploader")
    self.privacyStatus.addItems(['public', 'unlisted', 'private'])
    #extract user inputs from UI
    self.browsebutton.clicked.connect(self.browseFiles)
    self.publishVideo.clicked.connect(self.setVideoName)
    self.publishVideo.clicked.connect(self.setDescription)
    self.publishVideo.clicked.connect(self.setPrivacy)
    self.publishVideo.clicked.connect(self.submit)

  def browseFiles(self):
    file_name = QFileDialog.getOpenFileName(self)
    self.filename.setText(file_name[0])
    self.video_file_path = file_name[0]
  
  def setVideoName(self):
    self.video_name = self.titleName.text()
    
  def setDescription(self):
    self.video_desc = self.video_description.text()
    
  def setPrivacy(self):
    self.video_privacy = self.privacyStatus.currentText()

  def submit(self):
    error_msg = QMessageBox()
    youtube_formats_lower = [(format.lower()) for format in YOUTUBE_FORMATS]
    if not self.video_file_path.endswith(tuple(youtube_formats_lower)):
      error_msg.setText("oh no that file is not a valid youtube format!")
      error_msg.exec()
    elif not self.video_name and not self.video_file_path:
      error_msg.setText("oh no you forgot to put a title and a file!")
      error_msg.exec()
    elif not self.video_name:
      error_msg.setText("oh no you forgot to put a title")
      error_msg.exec()
    elif not self.video_file_path:
      error_msg.setText("oh no you forgot to put a file!")
      error_msg.exec()
    else:
      youtube = get_authenticated_service(self)
      try:
        initialize_upload(youtube, self)
      except HttpError as e:
        print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))  

if __name__ == '__main__':
  app = QApplication(sys.argv)
  #begin UI
  ui = Main()
  ui.show()
  app.exec_()