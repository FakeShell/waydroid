# Copyright 2021 Erfan Abdi
# SPDX-License-Identifier: GPL-3.0-or-later
import logging
import os
import threading
import tools.config
import tools.helpers.net
from tools.helpers import ipc
from tools.interfaces import IUserMonitor
from tools.interfaces import IPlatform

stopping = False

def start(args, session, unlocked_cb=None):
    waydroid_data = session["waydroid_data"]
    apps_dir = session["xdg_data_home"] + "/applications/"

    def makeDesktopFile(appInfo):
        if appInfo is None:
            return -1

        showApp = False
        for cat in appInfo["categories"]:
            if cat.strip() == "android.intent.category.LAUNCHER":
                showApp = True
        if not showApp:
            return -1

        packageName = appInfo["packageName"]

        hide = False
        # FuriOS: don't add an icon for default apps such as documents, settings or microG
        if packageName == "com.android.documentsui" or packageName == "com.android.inputmethod.latin" \
            or packageName == "com.android.settings" or packageName == "com.google.android.gms" \
            or packageName == "org.lineageos.jelly" or packageName == "org.lineageos.aperture" \
            or packageName == "com.android.messaging" or packageName == "com.android.dialer":
            hide = True

        desktop_file_path = apps_dir + "/waydroid." + packageName + ".desktop"
        if not os.path.exists(desktop_file_path):
            with open(desktop_file_path, "w") as desktop_file:
                desktop_file.write(f"""\
[Desktop Entry]
Type=Application
Name={appInfo["name"]}
Exec=waydroid app launch {packageName}
Icon={waydroid_data}/icons/{packageName}.png
Categories=X-WayDroid-App;
X-Purism-FormFactor=Workstation;Mobile;
Actions=app_settings;
NoDisplay={str(hide).lower()}

[Desktop Action app_settings]
Name=App Settings
Exec=waydroid app intent android.settings.APPLICATION_DETAILS_SETTINGS package:{packageName}
Icon={waydroid_data}/icons/com.android.settings.png
""")
            return 0

    def makeWaydroidDesktopFile(hide):
        desktop_file_path = apps_dir + "/Waydroid.desktop"
        if os.path.isfile(desktop_file_path):
            os.remove(desktop_file_path)

        # FuriOS: we are not using this
        return -1

        with open(desktop_file_path, "w") as desktop_file:
            desktop_file.write(f"""\
[Desktop Entry]
Type=Application
Name=Waydroid
Exec=waydroid show-full-ui
Categories=X-WayDroid-App;
X-Purism-FormFactor=Workstation;Mobile;
Icon=waydroid
NoDisplay={str(hide).lower()}
""")

    def userUnlocked(uid):
        cfg = tools.config.load(args)
        logging.info("Android with user {} is ready".format(uid))

        if cfg["waydroid"]["auto_adb"] == "True":
            tools.helpers.net.adb_connect(args)

        platformService = IPlatform.get_service(args)
        if platformService:
            if not os.path.exists(apps_dir):
                os.mkdir(apps_dir, 0o700)
            appsList = platformService.getAppsInfo()
            for app in appsList:
                makeDesktopFile(app)
            multiwin = platformService.getprop("persist.waydroid.multi_windows", "false")
            makeWaydroidDesktopFile(multiwin == "true")
        if unlocked_cb:
            unlocked_cb()

        cm = ipc.DBusContainerService()
        cm.ForceFinishSetup()

        timezone = get_timezone()
        if timezone:
            cm.Setprop("persist.sys.timezone", timezone)

    def packageStateChanged(mode, packageName, uid):
        platformService = IPlatform.get_service(args)
        if platformService:
            appInfo = platformService.getAppInfo(packageName)
            desktop_file_path = apps_dir + "/waydroid." + packageName + ".desktop"
            if mode == 0:
                # Package added
                makeDesktopFile(appInfo)
            elif mode == 1:
                if os.path.isfile(desktop_file_path):
                    os.remove(desktop_file_path)
            else:
                if os.path.isfile(desktop_file_path):
                    if makeDesktopFile(appInfo) == -1:
                        os.remove(desktop_file_path)

    def service_thread():
        while not stopping:
            IUserMonitor.add_service(args, userUnlocked, packageStateChanged)

    global stopping
    stopping = False
    args.user_manager = threading.Thread(target=service_thread)
    args.user_manager.start()

def stop(args):
    global stopping
    stopping = True
    try:
        if args.userMonitorLoop:
            args.userMonitorLoop.quit()
    except AttributeError:
        logging.debug("UserMonitor service is not even started")

def get_timezone():
    localtime_path = '/etc/localtime'

    try:
        if os.path.exists(localtime_path):
            if os.path.islink(localtime_path):
                target = os.readlink(localtime_path)
                timezone = '/'.join(target.split('/')[-2:])
                return timezone
    except Exception as e:
        logging.error(f"Failed to get timezone: {e}")
    return False
