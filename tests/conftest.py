import os

# Importing the app would otherwise start the connection-log poller, which
# shells out to nordvpn and writes to data/ in the background during tests.
os.environ["NORDMESH_DISABLE_POLLER"] = "1"
