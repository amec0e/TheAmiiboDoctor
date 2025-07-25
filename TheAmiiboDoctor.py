#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TheAmiiboDoctor
Automatically fixes CT in SN3, Password, PACK, BCC0, BCC1, UID, DLB, and CFG issues in .nfc and .bin files
Creates backups in a dedicated folder before making changes
"""

import os
import re
import sys
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def backup_file(filepath, backup_timestamp, base_directory, backup_tracker=None):
    """Create a backup of the original file in a timestamped backup folder at the base directory level"""
    try:
        if backup_tracker is None:
            backup_tracker = set()
        
        file_key = str(filepath.resolve())
        if file_key in backup_tracker:
            return None

        backup_tracker.add(file_key)
        backup_dir = base_directory / f"backup_{backup_timestamp}"
        relative_path = filepath.relative_to(base_directory)
        backup_path = backup_dir / relative_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(filepath, backup_path)
        print(f"📁 Backed up: {relative_path}")
        return backup_path
    except Exception as e:
        print(f"❌ Warning: Could not create backup for {filepath}: {e}")
        return None

def extract_version_from_nfc(filepath):
    """Extract version number from .nfc file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        for line in lines:
            version_match = re.search(r'Version:\s*(\d+)', line)
            if version_match:
                return int(version_match.group(1))
        
        return None
            
    except Exception as e:
        return None

def extract_pages_from_nfc(filepath):
    """Extract pages 0, 1, 2, 130, 131, 132, 133, 134 from .nfc file, UID field, and version"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        pages = {}
        lines = content.split('\n')
        uid_field = None
        version = None
        
        for line in lines:
            uid_match = re.search(r'UID:\s*([0-9A-Fa-f\s]+)', line)
            if uid_match:
                uid_field = uid_match.group(1).replace(' ', '').upper()
            
            version_match = re.search(r'Version:\s*(\d+)', line)
            if version_match:
                version = int(version_match.group(1))
            
            page_match = re.search(r'Page\s+(\d+):\s*([0-9A-Fa-f\s]+)', line)
            if page_match:
                page_num = int(page_match.group(1))
                page_data = page_match.group(2).replace(' ', '')
                pages[page_num] = page_data
        
        return pages, content, lines, uid_field, version
            
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None, None, None, None, None

def extract_pages_from_bin(filepath):
    """Extract pages 0, 1, 2, 130, 131, 132, 133, 134 from .bin file"""
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        if len(data) < 540:
            return None, None

        pages = {}
        for page_num in [0, 1, 2, 130, 131, 132, 133, 134]:
            if page_num * 4 + 4 <= len(data):
                page_data = data[page_num * 4:(page_num * 4) + 4]
                pages[page_num] = page_data.hex().upper()
        
        return pages, data
            
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None, None

def calculate_password_from_uid(uid_bytes):
    """Calculate expected password from UID"""
    if len(uid_bytes) < 7:
        return None
    
    sn0, sn1, sn2, sn3, sn4, sn5, sn6 = uid_bytes[0], uid_bytes[1], uid_bytes[2], uid_bytes[3], uid_bytes[4], uid_bytes[5], uid_bytes[6]
    
    pwd = []
    pwd.append(sn1 ^ sn3 ^ 0xAA)  # SN1 ^ SN3 ^ 0xAA
    pwd.append(sn2 ^ sn4 ^ 0x55)  # SN2 ^ SN4 ^ 0x55
    pwd.append(sn3 ^ sn5 ^ 0xAA)  # SN3 ^ SN5 ^ 0xAA
    pwd.append(sn4 ^ sn6 ^ 0x55)  # SN4 ^ SN6 ^ 0x55
    
    return bytes(pwd)

def generate_new_uid():
    """Generate a new valid UID that doesn't have 0x88 in SN3 position"""
    import random
    
    uid_bytes = []
    for i in range(7):
        if i == 3:
            byte_val = random.randint(0, 255)
            while byte_val == 0x88:
                byte_val = random.randint(0, 255)
            uid_bytes.append(byte_val)
        else:
            uid_bytes.append(random.randint(0, 255))
    
    return uid_bytes
    
def convert_nfc_to_v4(filepath, backup_timestamp, base_directory, backup_tracker=None):
    """Convert V2 or V3 NFC files to V4 format"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        version = None
        pages = {}

        for line in lines:
            version_match = re.search(r'Version:\s*(\d+)', line)
            if version_match:
                version = int(version_match.group(1))
            
            page_match = re.search(r'Page\s+(\d+):\s*([0-9A-Fa-f\s]+)', line)
            if page_match:
                page_num = int(page_match.group(1))
                page_data = page_match.group(2).replace(' ', '')
                pages[page_num] = page_data
        
        if version == 4:
            return True, "Already V4", {}
        
        if version not in [2, 3]:
            return False, f"Unsupported version: {version}", {}
        
        backup_path = backup_file(filepath, backup_timestamp, base_directory, backup_tracker)
        new_content = convert_to_v4_format(pages, lines)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        backup_info = f"backup: {backup_path.name}" if backup_path else "already backed up"
        return True, f"Converted V{version} to V4 ({backup_info})", {"version_conversion": True}
        
    except Exception as e:
        return False, f"Error converting file: {e}", {}

def convert_to_v4_format(pages, original_lines):
    """Convert page data to V4 NFC format"""
    if 0 in pages and 1 in pages:
        page0_bytes = bytes.fromhex(pages[0])
        page1_bytes = bytes.fromhex(pages[1])
        uid_bytes = page0_bytes[:3] + page1_bytes[:4]
        uid_hex = ' '.join(f'{b:02X}' for b in uid_bytes)
    else:
        uid_hex = "04 AB 73 54 B8 B6 0F"
    page_count = max(pages.keys()) + 1 if pages else 135
    v4_content = f"""Filetype: Flipper NFC device
Version: 4
# Device type can be ISO14443-3A, ISO14443-3B, ISO14443-4A, ISO14443-4B, ISO15693-3, FeliCa, NTAG/Ultralight, Mifare Classic, Mifare Plus, Mifare DESFire, SLIX, ST25TB, EMV
Device type: NTAG/Ultralight
# UID is common for all formats
UID: {uid_hex}
# ISO14443-3A specific data
ATQA: 00 44
SAK: 00
# NTAG/Ultralight specific data
Data format version: 2
NTAG/Ultralight type: NTAG215
Signature: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
Mifare version: 00 04 04 02 01 00 11 03
Counter 0: 0
Tearing 0: 00
Counter 1: 0
Tearing 1: 00
Counter 2: 0
Tearing 2: 00
Pages total: {page_count}
Pages read: {page_count}"""
    
    page_lines = []
    for page_num in range(page_count):
        if page_num in pages:
            page_data = pages[page_num]
            formatted_data = ' '.join(page_data[i:i+2] for i in range(0, len(page_data), 2))
            page_lines.append(f"Page {page_num}: {formatted_data.upper()}")
        else:
            page_lines.append(f"Page {page_num}: 00 00 00 00")
    
    v4_content += "\n" + "\n".join(page_lines) + "\n"
    v4_content += "Failed authentication attempts: 0" + "\n"
    
    return v4_content

def fix_uid_if_sn3_is_88(uid_bytes):
    """Fix UID if SN3 (4th byte) is 0x88 by generating a random replacement"""
    import random
    
    if len(uid_bytes) >= 4 and uid_bytes[3] == 0x88:
        new_sn3 = random.randint(0, 255)
        while new_sn3 == 0x88:
            new_sn3 = random.randint(0, 255)
        
        uid_bytes = list(uid_bytes)
        uid_bytes[3] = new_sn3
        return bytes(uid_bytes), True
    
    return uid_bytes, False

def validate_dlb_and_cfg(pages):
    """Validate DLB (Page 130) and CFG0/CFG1 (Pages 131/132)"""
    if not pages or 130 not in pages or 131 not in pages or 132 not in pages:
        return False, "Missing DLB/CFG pages", False, False, False
    
    page130 = bytes.fromhex(pages[130])  # DLB (Dynamic Lock Bytes)
    page131 = bytes.fromhex(pages[131])  # CFG0
    page132 = bytes.fromhex(pages[132])  # CFG1
    
    if len(page130) < 4 or len(page131) < 4 or len(page132) < 4:
        return False, "Invalid DLB/CFG page lengths", False, False, False
    
    expected_dlb = bytes([0x01, 0x00, 0x0F, 0xBF])    # Page 130
    expected_cfg0 = bytes([0x00, 0x00, 0x00, 0x04])   # Page 131
    expected_cfg1 = bytes([0x5F, 0x00, 0x00, 0x00])   # Page 132
    
    actual_dlb = page130[:4]
    actual_cfg0 = page131[:4]
    actual_cfg1 = page132[:4]
    
    dlb_valid = actual_dlb == expected_dlb
    cfg0_valid = actual_cfg0 == expected_cfg0
    cfg1_valid = actual_cfg1 == expected_cfg1
    
    dlb_hex = ' '.join(f'{b:02X}' for b in actual_dlb)
    cfg0_hex = ' '.join(f'{b:02X}' for b in actual_cfg0)
    cfg1_hex = ' '.join(f'{b:02X}' for b in actual_cfg1)
    
    status_parts = []
    if dlb_valid:
        status_parts.append(f"DLB={dlb_hex} ✓")
    else:
        status_parts.append(f"DLB={dlb_hex} ✗ (expected 01 00 0F BF)")
    
    if cfg0_valid:
        status_parts.append(f"CFG0={cfg0_hex} ✓")
    else:
        status_parts.append(f"CFG0={cfg0_hex} ✗ (expected 00 00 00 04)")
    
    if cfg1_valid:
        status_parts.append(f"CFG1={cfg1_hex} ✓")
    else:
        status_parts.append(f"CFG1={cfg1_hex} ✗ (expected 5F 00 00 00)")
    
    all_valid = dlb_valid and cfg0_valid and cfg1_valid
    status = ", ".join(status_parts)
    
    return all_valid, status, dlb_valid, cfg0_valid, cfg1_valid

def check_uid_comprehensive(pages, filepath, uid_field=None):
    """Comprehensive UID validation: 4th position, BCC, password, PACK, DLB, and CFG"""
    if not pages or 0 not in pages or 1 not in pages:
        return False, "Missing required pages", "", {"uid_field": False, "sn3": False, "bcc0": False, "bcc1": False, "password": False, "pack": False, "dlb": False, "cfg0": False, "cfg1": False}
    
    page0 = bytes.fromhex(pages[0])
    page1 = bytes.fromhex(pages[1])
    uid_bytes = page0[:3] + page1[:4]
    
    if len(uid_bytes) < 7:
        return False, "Invalid UID length", "", {"uid_field": False, "sn3": False, "bcc0": False, "bcc1": False, "password": False, "pack": False, "dlb": False, "cfg0": False, "cfg1": False}
    
    sn0, sn1, sn2, sn3, sn4, sn5, sn6 = uid_bytes
    uid_hex = ' '.join(f'{b:02X}' for b in uid_bytes)
    
    if uid_field is not None:
        if len(uid_field) != 14:
            uid_field_matches_pages = False
        else:
            try:
                constructed_uid = ''.join(f'{b:02X}' for b in uid_bytes)
                uid_field_matches_pages = uid_field == constructed_uid
            except:
                uid_field_matches_pages = False
    else:
        uid_field_matches_pages = True
    
    ct = 0x88
    expected_bcc0 = ct ^ sn0 ^ sn1 ^ sn2
    expected_bcc1 = sn3 ^ sn4 ^ sn5 ^ sn6
    
    if len(page0) >= 4:
        actual_bcc0 = page0[3]
        bcc0_valid = actual_bcc0 == expected_bcc0
    else:
        bcc0_valid = False
        actual_bcc0 = 0
    
    if 2 in pages:
        page2 = bytes.fromhex(pages[2])
        if len(page2) >= 1:
            actual_bcc1 = page2[0]
            bcc1_valid = actual_bcc1 == expected_bcc1
        else:
            bcc1_valid = False
            actual_bcc1 = 0
    else:
        bcc1_valid = False
        actual_bcc1 = 0
    
    if 133 in pages and 134 in pages:
        expected_password = calculate_password_from_uid(uid_bytes)
        page133 = bytes.fromhex(pages[133])
        page134 = bytes.fromhex(pages[134])
        
        if len(page133) >= 4 and len(page134) >= 4:
            actual_password = page133[:4]
            actual_pack = page134[:4]
            expected_pack = bytes([0x80, 0x80, 0x00, 0x00])
            
            password_valid = actual_password == expected_password
            pack_valid = actual_pack == expected_pack
        else:
            password_valid = False
            pack_valid = False
            actual_password = bytes(4)
            actual_pack = bytes(4)
    else:
        password_valid = False
        pack_valid = False
        actual_password = bytes(4)
        actual_pack = bytes(4)
        expected_password = calculate_password_from_uid(uid_bytes)
    
    dlb_cfg_valid, dlb_cfg_msg, dlb_valid, cfg0_valid, cfg1_valid = validate_dlb_and_cfg(pages)
    
    has_position_issue = sn3 == 0x88
    sn3_valid = not has_position_issue
    
    if has_position_issue:
        sn3_status = f"SN3=0x88 (PROBLEM!)"
    else:
        sn3_status = f"SN3=0x{sn3:02X} (OK)"
    
    if bcc0_valid:
        bcc0_msg = f"BCC0=0x{actual_bcc0:02X} ✓"
    else:
        bcc0_msg = f"BCC0=0x{actual_bcc0:02X} ✗ (expected 0x{expected_bcc0:02X})"
    
    if bcc1_valid:
        bcc1_msg = f"BCC1=0x{actual_bcc1:02X} ✓"
    else:
        bcc1_msg = f"BCC1=0x{actual_bcc1:02X} ✗ (expected 0x{expected_bcc1:02X})"
    
    bcc_msg = f"{bcc0_msg}, {bcc1_msg}"
    
    if password_valid and pack_valid:
        pwd_pack_msg = f"PWD={' '.join(f'{b:02X}' for b in actual_password)} ✓, PACK={' '.join(f'{b:02X}' for b in actual_pack)} ✓"
    elif password_valid and not pack_valid:
        pwd_pack_msg = f"PWD={' '.join(f'{b:02X}' for b in actual_password)} ✓, PACK={' '.join(f'{b:02X}' for b in actual_pack)} ✗ (expected 80 80 00 00)"
    elif not password_valid and pack_valid:
        expected_password_hex = ' '.join(f'{b:02X}' for b in expected_password)
        pwd_pack_msg = f"PWD={' '.join(f'{b:02X}' for b in actual_password)} ✗ (expected {expected_password_hex}), PACK={' '.join(f'{b:02X}' for b in actual_pack)} ✓"
    else:
        expected_password_hex = ' '.join(f'{b:02X}' for b in expected_password)
        pwd_pack_msg = f"PWD={' '.join(f'{b:02X}' for b in actual_password)} ✗ (expected {expected_password_hex}), PACK={' '.join(f'{b:02X}' for b in actual_pack)} ✗ (expected 80 80 00 00)"
    
    all_valid = sn3_valid and bcc0_valid and bcc1_valid and password_valid and pack_valid and dlb_cfg_valid
    
    status_parts = [sn3_status, bcc_msg, dlb_cfg_msg, pwd_pack_msg]
    if uid_field is not None and not uid_field_matches_pages:
        constructed_uid = ''.join(f'{b:02X}' for b in uid_bytes)
        status_parts.insert(0, f"UID field mismatch (field={uid_field}, pages={constructed_uid})")
    
    status = " + ".join(status_parts)
    
    problem_details = {
        "uid_field": uid_field_matches_pages,
        "sn3": sn3_valid,
        "bcc0": bcc0_valid,
        "bcc1": bcc1_valid,
        "password": password_valid,
        "pack": pack_valid,
        "dlb": dlb_valid,
        "cfg0": cfg0_valid,
        "cfg1": cfg1_valid
    }
    
    return all_valid, status, uid_hex, problem_details

def fix_nfc_file(filepath, backup_timestamp, base_directory, fix_uid=True, fix_bcc=True, fix_password=True, fix_pack=True, fix_dlb=True, fix_cfg=True, backup_tracker=None):
    """Fix all issues in an NFC file"""
    pages, original_content, lines, uid_field, version = extract_pages_from_nfc(filepath)
    
    if not pages:
        return False, "Could not read file", {}
    
    if 0 not in pages or 1 not in pages:
        return False, "Missing required pages 0 or 1", {}
    
    changes_made = []
    issue_types = {
        'uid_field': False,
        'sn3': False,
        'bcc0': False,
        'bcc1': False,
        'password': False,
        'pack': False,
        'dlb': False,
        'cfg0': False,
        'cfg1': False
    }
    
    page0_bytes = bytes.fromhex(pages[0])
    page1_bytes = bytes.fromhex(pages[1])
    uid_bytes = page0_bytes[:3] + page1_bytes[:4]
    
    if fix_uid and uid_field and len(uid_field) == 14:
        try:
            constructed_uid = ''.join(f'{b:02X}' for b in uid_bytes)
            if uid_field != constructed_uid:
                changes_made.append(f"Fixed UID field to match pages: {uid_field} -> {constructed_uid}")
                issue_types['uid_field'] = True
        except:
            pass
    
    if fix_uid:
        uid_bytes, sn3_was_fixed = fix_uid_if_sn3_is_88(uid_bytes)
        if sn3_was_fixed:
            changes_made.append(f"Fixed CT in SN3 from 0x88 to 0x{uid_bytes[3]:02X}")
            issue_types['sn3'] = True
    
    sn0, sn1, sn2, sn3, sn4, sn5, sn6 = uid_bytes
    ct = 0x88
    correct_bcc0 = ct ^ sn0 ^ sn1 ^ sn2
    correct_bcc1 = sn3 ^ sn4 ^ sn5 ^ sn6
    current_bcc0 = page0_bytes[3] if len(page0_bytes) >= 4 else 0
    
    if fix_bcc and current_bcc0 != correct_bcc0:
        changes_made.append(f"Fixed BCC0: {current_bcc0:02X} -> {correct_bcc0:02X}")
        issue_types['bcc0'] = True
    
    if fix_bcc and 2 in pages:
        page2_bytes = bytes.fromhex(pages[2])
        if len(page2_bytes) >= 1:
            current_bcc1 = page2_bytes[0]
            if current_bcc1 != correct_bcc1:
                changes_made.append(f"Fixed BCC1: {current_bcc1:02X} -> {correct_bcc1:02X}")
                issue_types['bcc1'] = True
    
    correct_password = list(calculate_password_from_uid(uid_bytes))
    
    if fix_password and 133 in pages:
        page133_bytes = bytes.fromhex(pages[133])
        if len(page133_bytes) >= 4:
            current_password = list(page133_bytes[:4])
            if current_password != correct_password:
                pwd_old = ' '.join(f'{b:02X}' for b in current_password)
                pwd_new = ' '.join(f'{b:02X}' for b in correct_password)
                changes_made.append(f"Fixed Password: {pwd_old} -> {pwd_new}")
                issue_types['password'] = True
    
    correct_pack = [0x80, 0x80, 0x00, 0x00]
    if fix_pack and 134 in pages:
        page134_bytes = bytes.fromhex(pages[134])
        if len(page134_bytes) >= 4:
            current_pack = list(page134_bytes[:4])
            if current_pack != correct_pack:
                pack_old = ' '.join(f'{b:02X}' for b in current_pack)
                pack_new = ' '.join(f'{b:02X}' for b in correct_pack)
                changes_made.append(f"Fixed PACK: {pack_old} -> {pack_new}")
                issue_types['pack'] = True
    
    correct_dlb = [0x01, 0x00, 0x0F, 0xBF]
    if fix_dlb and 130 in pages:
        page130_bytes = bytes.fromhex(pages[130])
        if len(page130_bytes) >= 4:
            current_dlb = list(page130_bytes[:4])
            if current_dlb != correct_dlb:
                dlb_old = ' '.join(f'{b:02X}' for b in current_dlb)
                dlb_new = ' '.join(f'{b:02X}' for b in correct_dlb)
                changes_made.append(f"Fixed DLB: {dlb_old} -> {dlb_new}")
                issue_types['dlb'] = True
    
    correct_cfg0 = [0x00, 0x00, 0x00, 0x04]
    if fix_cfg and 131 in pages:
        page131_bytes = bytes.fromhex(pages[131])
        if len(page131_bytes) >= 4:
            current_cfg0 = list(page131_bytes[:4])
            if current_cfg0 != correct_cfg0:
                cfg0_old = ' '.join(f'{b:02X}' for b in current_cfg0)
                cfg0_new = ' '.join(f'{b:02X}' for b in correct_cfg0)
                changes_made.append(f"Fixed CFG0: {cfg0_old} -> {cfg0_new}")
                issue_types['cfg0'] = True
    
    correct_cfg1 = [0x5F, 0x00, 0x00, 0x00]
    if fix_cfg and 132 in pages:
        page132_bytes = bytes.fromhex(pages[132])
        if len(page132_bytes) >= 4:
            current_cfg1 = list(page132_bytes[:4])
            if current_cfg1 != correct_cfg1:
                cfg1_old = ' '.join(f'{b:02X}' for b in current_cfg1)
                cfg1_new = ' '.join(f'{b:02X}' for b in correct_cfg1)
                changes_made.append(f"Fixed CFG1: {cfg1_old} -> {cfg1_new}")
                issue_types['cfg1'] = True
    
    if not changes_made:
        return True, "No changes needed", {}
    
    backup_path = backup_file(filepath, backup_timestamp, base_directory, backup_tracker)
    new_lines = []
    for line in lines:
        uid_match = re.search(r'UID:\s*([0-9A-Fa-f\s]+)', line)
        if uid_match and fix_uid:
            formatted_uid = f"{sn0:02X} {sn1:02X} {sn2:02X} {sn3:02X} {sn4:02X} {sn5:02X} {sn6:02X}"
            new_line = f"UID: {formatted_uid}"
            new_lines.append(new_line)
            continue
        
        page_match = re.search(r'Page\s+(\d+):\s*([0-9A-Fa-f\s]+)', line)
        if page_match:
            page_num = int(page_match.group(1))
            
            if page_num == 0 and (fix_uid or fix_bcc):
                new_page0 = f"{sn0:02X} {sn1:02X} {sn2:02X} {correct_bcc0:02X}"
                new_line = f"Page 0: {new_page0}"
                new_lines.append(new_line)
            elif page_num == 1 and fix_uid:
                new_page1 = f"{sn3:02X} {sn4:02X} {sn5:02X} {sn6:02X}"
                new_line = f"Page 1: {new_page1}"
                new_lines.append(new_line)
            elif page_num == 2 and fix_bcc:
                page2_bytes = bytes.fromhex(pages[2])
                new_page2 = f"{correct_bcc1:02X} {page2_bytes[1]:02X} {page2_bytes[2]:02X} {page2_bytes[3]:02X}"
                new_line = f"Page 2: {new_page2}"
                new_lines.append(new_line)
            elif page_num == 130 and fix_dlb:
                new_page130 = f"{correct_dlb[0]:02X} {correct_dlb[1]:02X} {correct_dlb[2]:02X} {correct_dlb[3]:02X}"
                new_line = f"Page 130: {new_page130}"
                new_lines.append(new_line)
            elif page_num == 131 and fix_cfg:
                new_page131 = f"{correct_cfg0[0]:02X} {correct_cfg0[1]:02X} {correct_cfg0[2]:02X} {correct_cfg0[3]:02X}"
                new_line = f"Page 131: {new_page131}"
                new_lines.append(new_line)
            elif page_num == 132 and fix_cfg:
                new_page132 = f"{correct_cfg1[0]:02X} {correct_cfg1[1]:02X} {correct_cfg1[2]:02X} {correct_cfg1[3]:02X}"
                new_line = f"Page 132: {new_page132}"
                new_lines.append(new_line)
            elif page_num == 133 and fix_password:
                new_page133 = f"{correct_password[0]:02X} {correct_password[1]:02X} {correct_password[2]:02X} {correct_password[3]:02X}"
                new_line = f"Page 133: {new_page133}"
                new_lines.append(new_line)
            elif page_num == 134 and fix_pack:
                new_page134 = f"{correct_pack[0]:02X} {correct_pack[1]:02X} {correct_pack[2]:02X} {correct_pack[3]:02X}"
                new_line = f"Page 134: {new_page134}"
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
   
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
       
        backup_info = f"backup: {backup_path.name}" if backup_path else "already backed up"
        return True, f"Fixed successfully ({backup_info}). Changes: {'; '.join(changes_made)}", issue_types
    except Exception as e:
        return False, f"Error writing file: {e}", {}

def fix_bin_file(filepath, backup_timestamp, base_directory, fix_uid=True, fix_bcc=True, fix_password=True, fix_pack=True, fix_dlb=True, fix_cfg=True, backup_tracker=None):
    """Fix all issues in a BIN file"""
    pages, original_data = extract_pages_from_bin(filepath)
    
    if not pages:
        return False, "Could not read file", {}
    
    if 0 not in pages or 1 not in pages:
        return False, "Missing required pages 0 or 1", {}
    
    changes_made = []
    issue_types = {
        'uid_field': False,
        'sn3': False,
        'bcc0': False,
        'bcc1': False,
        'password': False,
        'pack': False,
        'dlb': False,
        'cfg0': False,
        'cfg1': False
    }
    
    page0_bytes = bytes.fromhex(pages[0])
    page1_bytes = bytes.fromhex(pages[1])
    uid_bytes = page0_bytes[:3] + page1_bytes[:4]
    
    if fix_uid:
        uid_bytes, sn3_was_fixed = fix_uid_if_sn3_is_88(uid_bytes)
        if sn3_was_fixed:
            changes_made.append(f"Fixed CT in SN3 from 0x88 to 0x{uid_bytes[3]:02X}")
            issue_types['sn3'] = True
    
    sn0, sn1, sn2, sn3, sn4, sn5, sn6 = uid_bytes
    current_bcc0 = page0_bytes[3]
    ct = 0x88
    correct_bcc0 = ct ^ sn0 ^ sn1 ^ sn2
    correct_bcc1 = sn3 ^ sn4 ^ sn5 ^ sn6
    
    if fix_bcc and current_bcc0 != correct_bcc0:
        changes_made.append(f"Fixed BCC0: {current_bcc0:02X} -> {correct_bcc0:02X}")
        issue_types['bcc0'] = True
    
    if fix_bcc and 2 in pages:
        page2_bytes = bytes.fromhex(pages[2])
        if len(page2_bytes) >= 1:
            current_bcc1 = page2_bytes[0]
            if current_bcc1 != correct_bcc1:
                changes_made.append(f"Fixed BCC1: {current_bcc1:02X} -> {correct_bcc1:02X}")
                issue_types['bcc1'] = True
    
    correct_password = list(calculate_password_from_uid(uid_bytes))
    
    if fix_password and 133 in pages:
        page133_bytes = bytes.fromhex(pages[133])
        if len(page133_bytes) >= 4:
            current_password = list(page133_bytes[:4])
            if current_password != correct_password:
                pwd_old = ' '.join(f'{b:02X}' for b in current_password)
                pwd_new = ' '.join(f'{b:02X}' for b in correct_password)
                changes_made.append(f"Fixed Password: {pwd_old} -> {pwd_new}")
                issue_types['password'] = True
    
    correct_pack = [0x80, 0x80, 0x00, 0x00]
    if fix_pack and 134 in pages:
        page134_bytes = bytes.fromhex(pages[134])
        if len(page134_bytes) >= 4:
            current_pack = list(page134_bytes[:4])
            if current_pack != correct_pack:
                pack_old = ' '.join(f'{b:02X}' for b in current_pack)
                pack_new = ' '.join(f'{b:02X}' for b in correct_pack)
                changes_made.append(f"Fixed PACK: {pack_old} -> {pack_new}")
                issue_types['pack'] = True
    
    correct_dlb = [0x01, 0x00, 0x0F, 0xBF]
    if fix_dlb and 130 in pages:
        page130_bytes = bytes.fromhex(pages[130])
        if len(page130_bytes) >= 4:
            current_dlb = list(page130_bytes[:4])
            if current_dlb != correct_dlb:
                dlb_old = ' '.join(f'{b:02X}' for b in current_dlb)
                dlb_new = ' '.join(f'{b:02X}' for b in correct_dlb)
                changes_made.append(f"Fixed DLB: {dlb_old} -> {dlb_new}")
                issue_types['dlb'] = True
    
    correct_cfg0 = [0x00, 0x00, 0x00, 0x04]
    if fix_cfg and 131 in pages:
        page131_bytes = bytes.fromhex(pages[131])
        if len(page131_bytes) >= 4:
            current_cfg0 = list(page131_bytes[:4])
            if current_cfg0 != correct_cfg0:
                cfg0_old = ' '.join(f'{b:02X}' for b in current_cfg0)
                cfg0_new = ' '.join(f'{b:02X}' for b in correct_cfg0)
                changes_made.append(f"Fixed CFG0: {cfg0_old} -> {cfg0_new}")
                issue_types['cfg0'] = True
    
    correct_cfg1 = [0x5F, 0x00, 0x00, 0x00]
    if fix_cfg and 132 in pages:
        page132_bytes = bytes.fromhex(pages[132])
        if len(page132_bytes) >= 4:
            current_cfg1 = list(page132_bytes[:4])
            if current_cfg1 != correct_cfg1:
                cfg1_old = ' '.join(f'{b:02X}' for b in current_cfg1)
                cfg1_new = ' '.join(f'{b:02X}' for b in correct_cfg1)
                changes_made.append(f"Fixed CFG1: {cfg1_old} -> {cfg1_new}")
                issue_types['cfg1'] = True
    
    if not changes_made:
        return True, "No changes needed", {}
    
    backup_path = backup_file(filepath, backup_timestamp, base_directory, backup_tracker)
    new_data = bytearray(original_data)

    if fix_uid:
        new_data[0] = sn0  # SN0
        new_data[1] = sn1  # SN1
        new_data[2] = sn2  # SN2
    if fix_bcc:
        new_data[3] = correct_bcc0  # BCC0
    
    if fix_uid:
        new_data[4] = sn3  # SN3
        new_data[5] = sn4  # SN4
        new_data[6] = sn5  # SN5
        new_data[7] = sn6  # SN6
    
    if fix_bcc and 2 in pages:
        new_data[8] = correct_bcc1
    
    if fix_dlb and 130 in pages:
        new_data[520:524] = bytes(correct_dlb)
    
    if fix_cfg and 131 in pages:
        new_data[524:528] = bytes(correct_cfg0)
    
    if fix_cfg and 132 in pages:
        new_data[528:532] = bytes(correct_cfg1)
    
    if fix_password and 133 in pages:
        new_data[532:536] = bytes(correct_password)
    
    if fix_pack and 134 in pages:
        new_data[536:540] = bytes(correct_pack)
    
    try:
        with open(filepath, 'wb') as f:
            f.write(new_data)
        
        backup_info = f"backup: {backup_path.name}" if backup_path else "already backed up"
        return True, f"Fixed successfully ({backup_info}). Changes: {'; '.join(changes_made)}", issue_types
    except Exception as e:
        return False, f"Error writing file: {e}", {}

def scan_and_fix_directory(directory, fix_uid=True, fix_bcc=True, fix_password=True, fix_pack=True, fix_dlb=True, fix_cfg=True, convert_to_v4=False, dry_run=False):
    """Scan directory and fix all NFC and BIN files"""
    directory = Path(directory)
    
    if not directory.exists():
        print(f"Directory {directory} does not exist!")
        return
    
    backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_tracker = set()
    
    mode = "DRY RUN" if dry_run else "FIXING"
    conversion_note = " + V2/V3→V4" if convert_to_v4 else ""
    print(f"🔧 {mode}: Scanning {directory} for NTAG215 NFC and BIN files to fix{conversion_note}...\n")
    
    if dry_run:
        print("⚠️  DRY RUN MODE - No files will be modified!\n")
    
    all_files = []
    
    for ext in ['*.nfc', '*.bin']:
        for filepath in directory.rglob(ext):
            if any(part.lower().startswith('backup') for part in filepath.parts):
                continue
                
            if filepath.suffix.lower() == '.nfc':
                pages, _, _, uid_field, version = extract_pages_from_nfc(filepath)
                needs_conversion = convert_to_v4 and version in [2, 3]
                
                if dry_run:
                    is_valid, status, uid_hex, problem_details = check_uid_comprehensive(pages, filepath.relative_to(directory), uid_field)
                    
                    conversion_status = ""
                    if needs_conversion:
                        conversion_status = f" (would convert V{version}→V4)"
                    
                    all_files.append({
                        'path': filepath.relative_to(directory),
                        'is_valid': is_valid,
                        'status': status + conversion_status,
                        'uid_hex': uid_hex,
                        'problems': problem_details,
                        'was_fixed': False,
                        'was_converted': False,
                        'file_type': 'nfc',
                        'version': version
                    })
                else:
                    original_is_valid, original_status, original_uid_hex, original_problems = check_uid_comprehensive(pages, filepath.relative_to(directory), uid_field)
                    was_converted = False
                    was_fixed = False
                    
                    if needs_conversion:
                        success, message, issue_types = convert_nfc_to_v4(filepath, backup_timestamp, directory, backup_tracker)
                        if success and issue_types.get('version_conversion', False):
                            was_converted = True
                            pages, _, _, uid_field, version = extract_pages_from_nfc(filepath)
                    
                    is_valid, status, uid_hex, problem_details = check_uid_comprehensive(pages, filepath.relative_to(directory), uid_field)
                    
                    if not is_valid:
                        success, message, issue_types = fix_nfc_file(filepath, backup_timestamp, directory, fix_uid, fix_bcc, fix_password, fix_pack, fix_dlb, fix_cfg, backup_tracker)
                        if success and any(issue_types.values()):
                            was_fixed = True
                            pages_new, _, _, uid_field_new, version_new = extract_pages_from_nfc(filepath)
                            is_valid, status, uid_hex, problem_details = check_uid_comprehensive(pages_new, filepath.relative_to(directory), uid_field_new)
                    
                    all_files.append({
                        'path': filepath.relative_to(directory),
                        'is_valid': is_valid,
                        'status': status,
                        'uid_hex': uid_hex,
                        'problems': problem_details,
                        'was_fixed': was_fixed,
                        'was_converted': was_converted,
                        'file_type': 'nfc',
                        'version': version
                    })
            
            elif filepath.suffix.lower() == '.bin':
                pages, _ = extract_pages_from_bin(filepath)
                is_valid, status, uid_hex, problem_details = check_uid_comprehensive(pages, filepath.relative_to(directory))
                
                if dry_run:
                    all_files.append({
                        'path': filepath.relative_to(directory),
                        'is_valid': is_valid,
                        'status': status,
                        'uid_hex': uid_hex,
                        'problems': problem_details,
                        'was_fixed': False,
                        'was_converted': False,
                        'file_type': 'bin',
                        'version': None
                    })
                else:
                    original_status = status
                    original_valid = is_valid
                    was_fixed = False
                    if not is_valid:
                        success, message, issue_types = fix_bin_file(filepath, backup_timestamp, directory, fix_uid, fix_bcc, fix_password, fix_pack, fix_dlb, fix_cfg, backup_tracker)
                        if success and any(issue_types.values()):
                            was_fixed = True
                            pages_new, _ = extract_pages_from_bin(filepath)
                            is_valid_new, status_new, uid_hex_new, problem_details_new = check_uid_comprehensive(pages_new, filepath.relative_to(directory))
                            all_files.append({
                                'path': filepath.relative_to(directory),
                                'is_valid': is_valid_new,
                                'status': status_new,
                                'uid_hex': uid_hex_new,
                                'problems': problem_details_new,
                                'was_fixed': was_fixed,
                                'was_converted': False,
                                'file_type': 'bin',
                                'version': None
                            })
                        else:
                            all_files.append({
                                'path': filepath.relative_to(directory),
                                'is_valid': original_valid,
                                'status': original_status,
                                'uid_hex': uid_hex,
                                'problems': problem_details,
                                'was_fixed': was_fixed,
                                'was_converted': False,
                                'file_type': 'bin',
                                'version': None
                            })
                    else:
                        all_files.append({
                            'path': filepath.relative_to(directory),
                            'is_valid': original_valid,
                            'status': original_status,
                            'uid_hex': uid_hex,
                            'problems': problem_details,
                            'was_fixed': was_fixed,
                            'was_converted': False,
                            'file_type': 'bin',
                            'version': None
                        })
    
    all_files.sort(key=lambda x: str(x['path']).lower())
    valid_files = [f for f in all_files if f['is_valid']]
    problem_files = [f for f in all_files if not f['is_valid']]
    if valid_files:
        print("✅ VALID FILES:")
        print("-" * 70)
        for file_info in valid_files:
            if file_info['version'] is not None:
                version_str = f"v{file_info['version']}"
            else:
                version_str = ""
            
            file_type_indicator = f"[{file_info['file_type'].upper()}{version_str}]"
            status_parts = []
            if not dry_run:
                if file_info.get('was_fixed', False):
                    status_parts.append("FIXED")
                if file_info.get('was_converted', False):
                    status_parts.append("CONVERTED")
            
            if status_parts:
                print(f"✅ {file_info['path']} {file_type_indicator}: UID {file_info['uid_hex']} ({', '.join(status_parts)})")
            else:
                print(f"✅ {file_info['path']} {file_type_indicator}: UID {file_info['uid_hex']}")
            
            status = file_info['status']
            if "UID field mismatch" in status:
                uid_mismatch = re.search(r'UID field mismatch \(field=([0-9A-F]+), pages=([0-9A-F]+)\)', status)
                if uid_mismatch:
                    field_uid, page_uid = uid_mismatch.groups()
                    print(f"       UID field mismatch (field={field_uid}, pages={page_uid})")
            else:
                if file_info['file_type'] == 'nfc':
                    print(f"       UID field ✓")
            
            if "SN3=0x88 (PROBLEM!)" in status:
                print("       SN3=0x88 ✗")
            elif "SN3=" in status:
                sn3_match = re.search(r'SN3=0x([0-9A-F]+) \(OK\)', status)
                if sn3_match:
                    print(f"       SN3=0x{sn3_match.group(1)} ✓")
            
            bcc0_match = re.search(r'BCC0=0x([0-9A-F]+) ([✓✗])(?: \(expected 0x([0-9A-F]+)\))?', status)
            if bcc0_match:
                bcc0_val, bcc0_status, bcc0_expected = bcc0_match.groups()
                if bcc0_status == "✓":
                    print(f"       BCC0=0x{bcc0_val} ✓")
                else:
                    print(f"       BCC0=0x{bcc0_val} ✗ (expected 0x{bcc0_expected})")
            
            bcc1_match = re.search(r'BCC1=0x([0-9A-F]+) ([✓✗])(?: \(expected 0x([0-9A-F]+)\))?', status)
            if bcc1_match:
                bcc1_val, bcc1_status, bcc1_expected = bcc1_match.groups()
                if bcc1_status == "✓":
                    print(f"       BCC1=0x{bcc1_val} ✓")
                else:
                    print(f"       BCC1=0x{bcc1_val} ✗ (expected 0x{bcc1_expected})")
            
            dlb_match = re.search(r'DLB=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if dlb_match:
                dlb_val, dlb_status, dlb_expected = dlb_match.groups()
                if dlb_status == "✓":
                    print(f"       DLB={dlb_val} ✓")
                else:
                    print(f"       DLB={dlb_val} ✗ (expected {dlb_expected})")
            
            cfg0_match = re.search(r'CFG0=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if cfg0_match:
                cfg0_val, cfg0_status, cfg0_expected = cfg0_match.groups()
                if cfg0_status == "✓":
                    print(f"       CFG0={cfg0_val} ✓")
                else:
                    print(f"       CFG0={cfg0_val} ✗ (expected {cfg0_expected})")
            
            cfg1_match = re.search(r'CFG1=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if cfg1_match:
                cfg1_val, cfg1_status, cfg1_expected = cfg1_match.groups()
                if cfg1_status == "✓":
                    print(f"       CFG1={cfg1_val} ✓")
                else:
                    print(f"       CFG1={cfg1_val} ✗ (expected {cfg1_expected})")
            
            pwd_match = re.search(r'PWD=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if pwd_match:
                pwd_val, pwd_status, pwd_expected = pwd_match.groups()
                if pwd_status == "✓":
                    print(f"       PWD={pwd_val} ✓")
                else:
                    print(f"       PWD={pwd_val} ✗ (expected {pwd_expected})")
            
            pack_match = re.search(r'PACK=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if pack_match:
                pack_val, pack_status, pack_expected = pack_match.groups()
                if pack_status == "✓":
                    print(f"       PACK={pack_val} ✓")
                else:
                    print(f"       PACK={pack_val} ✗ (expected {pack_expected})")
            
            print()
    
    if problem_files:
        if valid_files:
            print("\n")
        if dry_run:
            print("🚨 ISSUES FOUND:")
        else:
            print("🚨 ISSUES (Could not be fixed):")
        print("-" * 70)
        for file_info in problem_files:
            if file_info['version'] is not None:
                version_str = f"v{file_info['version']}"
            else:
                version_str = ""
            
            file_type_indicator = f"[{file_info['file_type'].upper()}{version_str}]"
            
            print(f"🚨 {file_info['path']} {file_type_indicator}: UID {file_info['uid_hex']}")
            status = file_info['status']
            
            if "UID field mismatch" in status:
                uid_mismatch = re.search(r'UID field mismatch \(field=([0-9A-F]+), pages=([0-9A-F]+)\)', status)
                if uid_mismatch:
                    field_uid, page_uid = uid_mismatch.groups()
                    print(f"       UID field mismatch (field={field_uid}, pages={page_uid})")
            else:
                if file_info['file_type'] == 'nfc':
                    print(f"       UID field ✓")
            
            if "SN3=0x88 (PROBLEM!)" in status:
                print("       SN3=0x88 ✗")
            elif "SN3=" in status:
                sn3_match = re.search(r'SN3=0x([0-9A-F]+) \(OK\)', status)
                if sn3_match:
                    print(f"       SN3=0x{sn3_match.group(1)} ✓")
            
            bcc0_match = re.search(r'BCC0=0x([0-9A-F]+) ([✓✗])(?: \(expected 0x([0-9A-F]+)\))?', status)
            if bcc0_match:
                bcc0_val, bcc0_status, bcc0_expected = bcc0_match.groups()
                if bcc0_status == "✓":
                    print(f"       BCC0=0x{bcc0_val} ✓")
                else:
                    print(f"       BCC0=0x{bcc0_val} ✗ (expected 0x{bcc0_expected})")
            
            bcc1_match = re.search(r'BCC1=0x([0-9A-F]+) ([✓✗])(?: \(expected 0x([0-9A-F]+)\))?', status)
            if bcc1_match:
                bcc1_val, bcc1_status, bcc1_expected = bcc1_match.groups()
                if bcc1_status == "✓":
                    print(f"       BCC1=0x{bcc1_val} ✓")
                else:
                    print(f"       BCC1=0x{bcc1_val} ✗ (expected 0x{bcc1_expected})")
            
            dlb_match = re.search(r'DLB=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if dlb_match:
                dlb_val, dlb_status, dlb_expected = dlb_match.groups()
                if dlb_status == "✓":
                    print(f"       DLB={dlb_val} ✓")
                else:
                    print(f"       DLB={dlb_val} ✗ (expected {dlb_expected})")
            
            cfg0_match = re.search(r'CFG0=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if cfg0_match:
                cfg0_val, cfg0_status, cfg0_expected = cfg0_match.groups()
                if cfg0_status == "✓":
                    print(f"       CFG0={cfg0_val} ✓")
                else:
                    print(f"       CFG0={cfg0_val} ✗ (expected {cfg0_expected})")
            
            cfg1_match = re.search(r'CFG1=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if cfg1_match:
                cfg1_val, cfg1_status, cfg1_expected = cfg1_match.groups()
                if cfg1_status == "✓":
                    print(f"       CFG1={cfg1_val} ✓")
                else:
                    print(f"       CFG1={cfg1_val} ✗ (expected {cfg1_expected})")
            
            pwd_match = re.search(r'PWD=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if pwd_match:
                pwd_val, pwd_status, pwd_expected = pwd_match.groups()
                if pwd_status == "✓":
                    print(f"       PWD={pwd_val} ✓")
                else:
                    print(f"       PWD={pwd_val} ✗ (expected {pwd_expected})")
            
            pack_match = re.search(r'PACK=([0-9A-F\s]+) ([✓✗])(?: \(expected ([0-9A-F\s]+)\))?', status)
            if pack_match:
                pack_val, pack_status, pack_expected = pack_match.groups()
                if pack_status == "✓":
                    print(f"       PACK={pack_val} ✓")
                else:
                    print(f"       PACK={pack_val} ✗ (expected {pack_expected})")
            
            print()
    
    problem_stats = {
        "uid_field": 0,
        "sn3": 0,
        "bcc0": 0,
        "bcc1": 0,
        "password": 0,
        "pack": 0,
        "dlb": 0,
        "cfg0": 0,
        "cfg1": 0
    }
    
    for file_info in problem_files:
        problems = file_info['problems']
        if not problems.get('uid_field', True):
            problem_stats['uid_field'] += 1
        if not problems['sn3']:
            problem_stats['sn3'] += 1
        if not problems['bcc0']:
            problem_stats['bcc0'] += 1
        if not problems['bcc1']:
            problem_stats['bcc1'] += 1
        if not problems['password']:
            problem_stats['password'] += 1
        if not problems['pack']:
            problem_stats['pack'] += 1
        if not problems['dlb']:
            problem_stats['dlb'] += 1
        if not problems['cfg0']:
            problem_stats['cfg0'] += 1
        if not problems['cfg1']:
            problem_stats['cfg1'] += 1
    
    nfc_files = [f for f in all_files if f['file_type'] == 'nfc']
    bin_files = [f for f in all_files if f['file_type'] == 'bin']
    version_counts = defaultdict(int)
    for f in nfc_files:
        if f['version'] is not None:
            version_counts[f['version']] += 1
        else:
            version_counts['Unknown'] += 1

    total_files = len(all_files)
    problem_count = len(problem_files)
    valid_count = len(valid_files)
    fixed_count = len([f for f in all_files if f.get('was_fixed', False)])
    converted_count = len([f for f in all_files if f.get('was_converted', False)])
    
    print(f"\n{'='*70}")
    if dry_run:
        print(f"Scan Complete!")
    else:
        print(f"Processing Complete!")
    print(f"Total files checked: {total_files} ({len(nfc_files)} NFC, {len(bin_files)} BIN)")
    
    if nfc_files:
        version_breakdown = []
        for version, count in sorted(version_counts.items()):
            if version == 'Unknown':
                version_breakdown.append(f"{count} v?")
            else:
                version_breakdown.append(f"{count} v{version}")
        print(f"NFC versions: {', '.join(version_breakdown)}")
    
    print(f"Valid files: {valid_count}")
    print(f"Problem files: {problem_count}")
    if not dry_run:
        if fixed_count > 0:
            print(f"Files fixed: {fixed_count}")
        if converted_count > 0:
            print(f"Files converted to V4: {converted_count}")
    
    if problem_count > 0:
        print(f"\n📊 ISSUES BREAKDOWN:")
        print(f"   UID field mismatch:   {problem_stats['uid_field']} files")
        print(f"   CT in SN3 (0x88):     {problem_stats['sn3']} files")
        print(f"   BCC0 incorrect:       {problem_stats['bcc0']} files")
        print(f"   BCC1 incorrect:       {problem_stats['bcc1']} files")
        print(f"   DLB incorrect:        {problem_stats['dlb']} files")
        print(f"   CFG0 incorrect:       {problem_stats['cfg0']} files")
        print(f"   CFG1 incorrect:       {problem_stats['cfg1']} files")
        print(f"   Password incorrect:   {problem_stats['password']} files")
        print(f"   PACK incorrect:       {problem_stats['pack']} files")
        total_issues = sum(problem_stats.values())
        print(f"\n🚨 Total issues: {total_issues}")
        
        if dry_run:
            print(f"\n⚠️  Found {problem_count} files with issues!")
            if convert_to_v4:
                v2v3_files = len([f for f in all_files if f['version'] in [2, 3]])
                if v2v3_files > 0:
                    print(f"⚠️  Found {v2v3_files} V2/V3 files that would be converted to V4!")
            print("Use --fix to actually modify them.")
        else:
            if problem_count > 0:
                print(f"\nℹ️  {problem_count} files still have issues that could not be fixed.")
    else:
        print("\n🎉 All files passed validation!")
    
    if not dry_run and (fixed_count > 0 or converted_count > 0):
        actions = []
        if fixed_count > 0:
            actions.append(f"{fixed_count} files have been fixed")
        if converted_count > 0:
            actions.append(f"{converted_count} files have been converted to V4")
        print(f"\n✅ {' and '.join(actions)}!")
        print("📁 Original files backed up to timestamped backup folder maintaining directory structure.")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix NTAG215 NFC and BIN files for Flipper to Switch amiibo emulation')
    parser.add_argument('directory', help='Directory containing NFC and BIN files')
    parser.add_argument('--fix', action='store_true', help='Actually fix files (default is dry run)')
    parser.add_argument('--convert-v4', action='store_true', help='Convert V2/V3 NFC files to V4 format')
    parser.add_argument('--no-uid', action='store_true', help='Skip UID fixes')
    parser.add_argument('--no-bcc', action='store_true', help='Skip BCC fixes')
    parser.add_argument('--no-password', action='store_true', help='Skip password fixes')
    parser.add_argument('--no-pack', action='store_true', help='Skip PACK fixes')
    parser.add_argument('--no-dlb', action='store_true', help='Skip DLB fixes')
    parser.add_argument('--no-cfg', action='store_true', help='Skip CFG0/CFG1 fixes')
    
    args = parser.parse_args()
    fix_uid = not args.no_uid
    fix_bcc = not args.no_bcc
    fix_password = not args.no_password
    fix_pack = not args.no_pack
    fix_dlb = not args.no_dlb
    fix_cfg = not args.no_cfg
    
    dry_run = not args.fix
    
    scan_and_fix_directory(
        args.directory,
        fix_uid=fix_uid,
        fix_bcc=fix_bcc,
        fix_password=fix_password,
        fix_pack=fix_pack,
        fix_dlb=fix_dlb,
        fix_cfg=fix_cfg,
        convert_to_v4=args.convert_v4,
        dry_run=dry_run
    )

if __name__ == "__main__":
   main()