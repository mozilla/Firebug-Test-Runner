# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is the Firebug Test Runner.
#
# The Initial Developer of the Original Code is
# Andrew Halberstadt.
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
# Andrew Halberstadt - ahalberstadt@mozilla.com
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****

from mozrunner import FirefoxRunner
from mozprofile import FirefoxProfile
from optparse import OptionParser
from ConfigParser import ConfigParser
from time import sleep
import logging
import urllib2
import os, sys, platform

class FBRunner:
    def __init__(self, **kwargs):    
        # Set up the log file or use stdout if none specified
        logLevel = logging.DEBUG if kwargs["debug"] else logging.INFO
        filename = kwargs["log"]
        self.log = logging.getLogger("FIREBUG")
        if filename:
            dirname = os.path.dirname(filename)
            if dirname and not os.path.exists(dirname):
                os.makedirs(dirname)
            handler = logging.FileHandler(filename)
            format = "%(asctime)s - %(name)s %(levelname)s | %(message)s"
        else:
            handler = logging.StreamHandler()
            format = "%(name)s %(levelname)s | %(message)s"
        handler.setFormatter(logging.Formatter(format))
        self.log.addHandler(handler)
        self.log.setLevel(logLevel)
            
        # Initialization  
        self.binary = kwargs["binary"]
        self.profile = kwargs["profile"]
        self.serverpath = kwargs["serverpath"]
        self.version = kwargs["version"]
        self.testlist = kwargs["testlist"]
        self.platform = platform.system().lower()
        
        # Because the only communication between this script and the FBTest console is the
        # log file, we don't know whether there was a crash or the test is just taking awhile.
        # Make 1 minute the timeout for tests.
        self.TEST_TIMEOUT = 60        
        
        # Ensure serverpath has correct format
        self.serverpath = self.serverpath.rstrip("/") + "/"
        
        # Read in config file
        self.download(self.serverpath + "releases/firebug/test-bot.config", "test-bot.config")
        self.config = ConfigParser()
        self.config.read("test-bot.config")
        
        # Make sure we have a testlist
        if not self.testlist:
            self.testlist = self.config.get("Firebug"+self.version, "TEST_LIST")

    def cleanup(self):
        """
        Remove temporarily downloaded files
        """
        try:
            for tmpFile in ["firebug.xpi", "fbtest.xpi", "test-bot.config"]:
                if os.path.exists(tmpFile):
                    self.log.debug("Removing " + tmpFile)
                    os.remove(tmpFile)
        except Exception, e:
            self.log.warn("Could not clean up temporary files: " + str(e))
            
    def download(self, url, savepath):
        """
        Save the file located at 'url' into 'filename'
        """
        self.log.debug("Downloading '" + url + "' to '" + savepath + "'")
        ret = urllib2.urlopen(url)
        savedir = os.path.dirname(savepath)
        if savedir and not os.path.exists(savedir):
            os.makedirs(savedir)
        outfile = open(savepath, 'wb')
        outfile.write(ret.read())
        outfile.close()
        
    def get_extensions(self):
        """
        Downloads the firebug and fbtest extensions
        for the specified Firebug version
        """
        self.log.debug("Downloading firebug and fbtest extensions from server")
        FIREBUG_XPI = self.config.get("Firebug" + self.version, "FIREBUG_XPI")
        FBTEST_XPI = self.config.get("Firebug" + self.version, "FBTEST_XPI")
        self.download(FIREBUG_XPI, "firebug.xpi")
        self.download(FBTEST_XPI, "fbtest.xpi")

    def disable_compatibilityCheck(self):
        """
        Disables compatibility check which could
        potentially prompt the user for action
        """
        self.log.debug("Disabling compatibility check")
        try:
            app = ConfigParser()
            app.read(os.path.join(os.path.dirname(self.binary), "application.ini"))
            ver = app.get("App", "Version")
            ver = ver[:4] if ver[3]=="b" else ver[:3]      # Version should be of the form '3.6' or '4.0b' and not the whole string
            prefs = open(os.path.join(self.profile, "prefs.js"), "a")
            prefs.write("user_pref(\"extensions.checkCompatibility." + ver + "\", false);\n")
            prefs.close()
        except Exception, e:
            self.log.warn("Could not disable compatibility check: " + str(e))

    def run(self):
        """
        Code for running the tests
        """
        if self.profile:
            # Ensure the profile actually exists
            if not os.path.exists(self.profile):
                self.log.warn("Profile '" + self.profile + "' doesn't exist.  Creating temporary profile")
                self.profile = None
            else:
                # Move any potential existing log files to log_old folder
                if os.path.exists(os.path.join(self.profile, "firebug/fbtest/logs")):
                    self.log.debug("Moving existing log files to archive")
                    for name in os.listdir(os.path.join(self.profile, "firebug/fbtest/logs")):
                        os.rename(os.path.join(self.profile, "firebug/fbtest/logs", name), os.path.join(self.profile, "firebug/fbtest/logs_old", name))

        # Grab the extensions from server   
        try:
            self.get_extensions()
        except Exception, e:            
            self.log.error("Extensions could not be downloaded: " + str(e))
            self.cleanup()
            return -1

        # Create environment variables
        mozEnv = os.environ
        mozEnv["XPC_DEBUG_WARN"] = "warn"                # Suppresses certain alert warnings that may sometimes appear
        mozEnv["MOZ_CRASHREPORTER_NO_REPORT"] = "true"   # Disable crash reporter UI

        # Create profile for mozrunner and start the Firebug tests
        self.log.info("Starting Firebug Tests")
        try:
            self.log.debug("Creating Firefox profile and installing extensions")
            mozProfile = FirefoxProfile(profile=self.profile, addons=["firebug.xpi", "fbtest.xpi"])
            self.profile = mozProfile.profile
            
            # Disable the compatibility check on startup
            if self.binary:
                self.disable_compatibilityCheck()
            else:
                self.log.warn("Can't disable compatibility check because binary wasn't specified")

            self.log.debug("Running Firefox with cmdargs '-runFBTests " + self.testlist + "'")
            mozRunner = FirefoxRunner(profile=mozProfile, binary=self.binary, cmdargs=["-runFBTests", self.testlist], env=mozEnv)         
            mozRunner.start()
        except Exception, e:
            self.log.error("Could not start Firefox: " + str(e))
            self.cleanup()
            return -1

        # Find the log file
        timeout, logfile = 0, 0
        # Wait up to 60 seconds for the log file to be initialized
        while not logfile and timeout < 60:
            try:
                for name in os.listdir(os.path.join(self.profile, "firebug/fbtest/logs")):
                    logfile = open(os.path.join(self.profile, "firebug/fbtest/logs/", name))
            except OSError:
                timeout += 1
                sleep(1)
                
        # If log file was not found, create our own log file
        if not logfile:
            self.log.error("Could not find the log file in profile '" + self.profile + "'")
            self.cleanup()
            return -1 
        # If log file found, exit when fbtests finished (if no activity, wait up to 1 min)
        else:
            line, timeout = "", 0
            while timeout < self.TEST_TIMEOUT:
                line = logfile.readline()
                if line == "":
                    sleep(1)
                    timeout += 1
                else:
                    print line.rstrip()
                    if line.find("Test Suite Finished") != -1:
                        break
                    timeout = 0
        
        # If there was a timeout, then there was most likely a crash (however could also be failure in FBTest console or test itself)
        if timeout >= self.TEST_TIMEOUT:
            logfile.seek(1)
            line = logfile.readlines()[-1]
            if line.find("FIREBUG INFO") != -1:
                line = line[line.find("|") + 1:].lstrip()
                line = line[:line.find("|")].rstrip()
            else:
                line = "Unknown Test"
            print "FIREBUG TEST-UNEXPECTED-FAIL | " + line + " | Possible Firefox crash detected"       # Print out crash message with offending test
            self.log.warn("Possible crash detected - test run aborted")
            
        # Cleanup
        logfile.close()
        mozRunner.stop()
		self.cleanup()
        self.log.debug("Exiting - Status successful")
        return 0


# Called from the command line
def cli(argv=sys.argv[1:]):
    parser = OptionParser("usage: %prog [options]")
    parser.add_option("--appname", dest="binary",
                      help="Firefox binary path")
                    
    parser.add_option("--profile-path", dest="profile",
                      help="The profile to use when running Firefox")
                        
    parser.add_option("-s", "--serverpath", dest="serverpath", 
                      default="https://getfirebug.com/",
                      help="The http server containing the Firebug tests (default is https://getfirebug.com)")
                        
    parser.add_option("-v", "--version", dest="version",
                      default="1.7",
                      help="The firebug version to run (default is 1.7)")
                        
    parser.add_option("-t", "--testlist", dest="testlist",
                      help="Specify the name of the testlist to use, should usually use the default")
                      
    parser.add_option("--log", dest="log",
                      help="Path to the log file (default is stdout)")
                      
    parser.add_option("--debug", dest="debug",
                      action="store_true",
                      help="Enable debug logging")
    (opt, remainder) = parser.parse_args(argv)
    
    runner = FBRunner(binary=opt.binary, profile=opt.profile, serverpath=opt.serverpath, 
                                    version=opt.version, testlist=opt.testlist, log=opt.log, debug=opt.debug)
    return runner.run()

if __name__ == '__main__':
	sys.exit(cli())
