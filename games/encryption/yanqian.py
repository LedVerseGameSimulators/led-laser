# Source Generated with Decompyle++
# File: yanqian.pyc (Python 3.7)

import binascii
import ctypes
import shelve
import sys
import time
import rsa
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
import base64
from rsa import transform, core
from loguru import logger
from Crypto.Cipher import PKCS1_v1_5 as Cipher_pkcs1_v1_5
import sys
from ctypes import *
from model.setting import Setting
hinst = windll.LoadLibrary('./use_dll/Dongle_d.dll')

class DongleInfo(Structure):
    _fields_ = [
        ('m_Ver', c_ushort),
        ('m_Type', c_ushort),
        ('m_BirthDay', c_ubyte * 8),
        ('m_Agent', c_ulong),
        ('m_PID', c_ulong),
        ('m_UserID', c_ulong),
        ('m_HID', c_ubyte * 8),
        ('m_IsMother', c_ulong),
        ('m_DevType', c_ulong)]


def get_dgo_hd_id():
    don_Enm = hinst.Dongle_Enum
    dongle_info = DongleInfo()
    nCount = c_int(0)
    index = c_int(0)
    ret = don_Enm(byref(dongle_info), byref(nCount))
    hex_data = binascii.hexlify(dongle_info.m_HID).decode('utf-8')
    return hex_data


def ecpt_by_dgo(byte_info, encbuf):
    ret = 0
    index = c_int(0)
    handle = c_longlong(0)
    ret = hinst.Dongle_Open(byref(handle), index)
    nInDataLen = c_int(117)
    nOutDataLen = c_int(128)
    fileID = c_ushort(1)
    nFlag = c_int(0)
    rawbuf = c_ubyte * 128()
    for i in range(len(byte_info)):
        rawbuf[i] = c_ubyte(byte_info[i])
    
    ret = hinst.Dongle_RsaPri(handle, fileID, nFlag, rawbuf, nInDataLen, encbuf, byref(nOutDataLen))
    ret = hinst.Dongle_Close(handle)


def dcpt_by_pyt(info):
    str = '-----BEGIN RSA PUBLIC KEY-----\nMIGJAoGBAN0t8cbflWHP9t3TLiaxX+x2YMCG8//8EjowR/9bGEfk46ilfUwjLPx6QMp4tt6iVwcVOKVW2dxbHVJ7ZnVDzBi2xT9GEains3uCoiuvP5rgU2CXwKt5A/mn91prIu87/U87hUSL+FmcQ545H8XLNZU/bpDmG/RWl0jnB2JI8Uh9AgMBAAE=\n-----END RSA PUBLIC KEY-----'
    
    try:
        str = str.encode('utf-8')
        key = rsa.PublicKey.load_pkcs1(str)
        d = key.e
        n = key.n
        data_int = transform.bytes2int(info)
        decry = core.decrypt_int(data_int, d, n)
        out = transform.int2bytes(decry)
        sep_idx = out.index(b'\x00', 2)
        out = out[sep_idx + 1:]
    except:
        pass

    return out


def yanqian():
    info = get_dgo_hd_id()
    cur_time = time.time().__str__()
    info += cur_time
    byte_info = bytes(info, 'utf-8', **('encoding',))
    byte_info_supplement = bytearray()
    for i in range(0, 117):
        byte_info_supplement.append(i)
    
    for i in range(len(byte_info)):
        byte_info_supplement[i] = byte_info[i]
    
    encbuf = c_ubyte * 128()
    ecpt_by_dgo(byte_info_supplement, encbuf)
    infoafterdcpt = dcpt_by_pyt(encbuf)
    if binascii.hexlify(byte_info_supplement).decode('utf-8') == binascii.hexlify(infoafterdcpt).decode('utf-8'):
        return True
    return None

