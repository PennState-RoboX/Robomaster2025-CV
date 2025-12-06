import os
import sys
import cv2
import numpy as np

MVS_ROOT = r"C:\Users\sd190\temp\MVS"

def find_file(root: str, filename: str) -> str | None:
    for dirpath, _, filenames in os.walk(root):
        if filename in filenames:
            return os.path.join(dirpath, filename)
    return None

wrapper_py = find_file(MVS_ROOT, "MvCameraControl_class.py")
if not wrapper_py:
    raise FileNotFoundError(
        "Could not find MvCameraControl_class.py under:\n"
        f"  {MVS_ROOT}\n"
        "Your extracted/installed MVS tree doesn't contain the Python wrapper where expected."
    )

wrapper_dir = os.path.dirname(wrapper_py)
sys.path.insert(0, wrapper_dir)
print("Using Python wrapper from:", wrapper_dir)

dll_path = find_file(MVS_ROOT, "MvCameraControl.dll")
if not dll_path:
    raise FileNotFoundError(
        "Could not find MvCameraControl.dll under:\n"
        f"  {MVS_ROOT}\n"
        "This usually means the MVS Runtime (Win64/Win32) is not present in this folder.\n"
        "You may need to install MVS Runtime or copy the Runtime folder into this tree."
    )

dll_dir = os.path.dirname(dll_path)
print("Using DLL from:", dll_dir)

os.add_dll_directory(dll_dir)

for extra in (
    os.path.join(os.path.dirname(dll_dir), "Win64_x64"),
    os.path.join(os.path.dirname(dll_dir), "Win32"),
    os.path.join(MVS_ROOT, "Runtime", "Win64_x64"),
    os.path.join(MVS_ROOT, "Development", "Runtime", "Win64_x64"),
    os.path.join(MVS_ROOT, "Runtime", "Win32"),
    os.path.join(MVS_ROOT, "Development", "Runtime", "Win32"),
):
    if os.path.isdir(extra):
        os.add_dll_directory(extra)

# ---- 3) Import the wrapper (now module + DLL pathing are set up) ----
from MvCameraControl_class import *  # noqa: F401,F403

g_bExit = False


def hik_init():
    SDKVersion = MvCamera.MV_CC_GetSDKVersion()
    print("SDKVersion[0x%x]" % SDKVersion)

    deviceList = MV_CC_DEVICE_INFO_LIST()
    tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE

    ret = MvCamera.MV_CC_EnumDevices(tlayerType, deviceList)
    if ret != 0:
        print("enum devices fail! ret[0x%x]" % ret)
        sys.exit()

    if deviceList.nDeviceNum == 0:
        print("find no device!")
        sys.exit()

    print("Find %d devices!" % deviceList.nDeviceNum)

    for i in range(0, deviceList.nDeviceNum):
        mvcc_dev_info = cast(deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
        if mvcc_dev_info.nTLayerType == MV_GIGE_DEVICE:
            print("\ngige device: [%d]" % i)
            strModeName = ""
            for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chModelName:
                strModeName = strModeName + chr(per)
            print("device model name: %s" % strModeName)

            nip1 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24)
            nip2 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16)
            nip3 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8)
            nip4 = (mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
            print("current ip: %d.%d.%d.%d\n" % (nip1, nip2, nip3, nip4))

        elif mvcc_dev_info.nTLayerType == MV_USB_DEVICE:
            print("\nu3v device: [%d]" % i)
            strModeName = ""
            for per in mvcc_dev_info.SpecialInfo.stUsb3VInfo.chModelName:
                if per == 0:
                    break
                strModeName = strModeName + chr(per)
            print("device model name: %s" % strModeName)

            strSerialNumber = ""
            for per in mvcc_dev_info.SpecialInfo.stUsb3VInfo.chSerialNumber:
                if per == 0:
                    break
                strSerialNumber = strSerialNumber + chr(per)
            print("user serial number: %s" % strSerialNumber)

    nConnectionNum = 0
    cam = MvCamera()

    stDeviceList = cast(deviceList.pDeviceInfo[int(nConnectionNum)], POINTER(MV_CC_DEVICE_INFO)).contents

    ret = cam.MV_CC_CreateHandle(stDeviceList)
    if ret != 0:
        print("create handle fail! ret[0x%x]" % ret)
        sys.exit()

    ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
    if ret != 0:
        print("open device fail! ret[0x%x]" % ret)
        sys.exit()

    ret = cam.MV_CC_StartGrabbing()
    if ret != 0:
        print("start grabbing fail! ret[0x%x]" % ret)
        sys.exit()

    stParam = MVCC_INTVALUE()
    memset(byref(stParam), 0, sizeof(MVCC_INTVALUE))

    ret = cam.MV_CC_GetIntValue("PayloadSize", stParam)
    if ret != 0:
        print("get payload size fail! ret[0x%x]" % ret)
        sys.exit()

    nPayloadSize = stParam.nCurValue
    data_buf = (c_ubyte * nPayloadSize)()
    stFrameInfo = MV_FRAME_OUT_INFO_EX()
    memset(byref(stFrameInfo), 0, sizeof(stFrameInfo))

    info_lst = [cam, data_buf, nPayloadSize, stFrameInfo]

    for _ in range(5):
        ret = cam.MV_CC_GetOneFrameTimeout(data_buf, nPayloadSize, stFrameInfo, 5000)
        if ret != 0:
            print("pipeline broke while testing frame readability", ret)
            sys.exit()

    return info_lst


def read_hik_frame(info_lst):
    cam = info_lst[0]
    data_buf = info_lst[1]
    nPayloadSize = info_lst[2]
    stFrameInfo = info_lst[3]

    ret = cam.MV_CC_GetOneFrameTimeout(data_buf, nPayloadSize, stFrameInfo, 1000)
    if ret == 0:
        image = np.asarray(data_buf).reshape((stFrameInfo.nHeight, stFrameInfo.nWidth, -1))
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BAYER_RG2RGB)
        return rgb_image
    else:
        print("no data[0x%x] --- Hik" % ret)
        return None


def hik_close(info_lst):
    cam = info_lst[0]
    data_buf = info_lst[1]

    ret = cam.MV_CC_StopGrabbing()
    if ret != 0:
        print("stop grabbing fail! ret[0x%x]" % ret)
        del data_buf
        sys.exit()

    ret = cam.MV_CC_CloseDevice()
    if ret != 0:
        print("close device fail! ret[0x%x]" % ret)
        del data_buf
        sys.exit()

    ret = cam.MV_CC_DestroyHandle()
    if ret != 0:
        print("destroy handle fail! ret[0x%x]" % ret)
        del data_buf
        sys.exit()

    del data_buf
