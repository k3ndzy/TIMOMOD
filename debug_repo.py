#!/usr/bin/env python3
"""
Debug script to simulate TIMO MOD repository validation
Tests the exact same validation rules as the Swift app
"""

import json
import requests
import re
from urllib.parse import urlparse

# Constants from PackageRepositoryLimits
MAX_MANIFEST_BYTES = 5 * 1024 * 1024  # 5MB
MAX_NAME_BYTES = 160
MAX_SUMMARY_BYTES = 500
MAX_DESCRIPTION_BYTES = 8192
MAX_CHANGELOG_BYTES = 32768
MAX_TAG_COUNT = 24
MAX_TAG_BYTES = 80
MAX_PACKAGE_COUNT = 5000
MAX_IDENTIFIER_BYTES = 128
MAX_SCREENSHOT_COUNT = 12

# Constants from PatchPackageLimits  
MAX_AUTHOR_BYTES = 160
MAX_PASSWORD_BYTES = 1024

def validate_url(url_str):
    """Simulate PackageRepositoryURLPolicy.validate()"""
    try:
        url = urlparse(url_str)
        
        # Must be HTTPS
        if url.scheme.lower() != 'https':
            return False, "Not HTTPS"
            
        # Must have host
        if not url.hostname:
            return False, "No hostname"
            
        # No auth, fragment
        if url.username or url.password or url.fragment:
            return False, "Has auth or fragment"
            
        # Port check (443 or None)
        if url.port and url.port != 443:
            return False, f"Invalid port: {url.port}"
            
        # Hostname checks
        host = url.hostname.lower()
        if (host == "localhost" or 
            host.endswith(".localhost") or 
            host.endswith(".local")):
            return False, f"Invalid hostname: {host}"
            
        # IP literal check (simplified)
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', host):
            return False, f"IP literal not allowed: {host}"
            
        return True, "Valid"
        
    except Exception as e:
        return False, f"Parse error: {e}"

def validate_text(text, max_bytes, required=True):
    """Simulate isValidText()"""
    if text is None:
        return not required, "Null text" if required else "OK (null)"
    
    if not isinstance(text, str):
        return False, "Not string"
        
    trimmed = text.strip()
    if required and not trimmed:
        return False, "Empty after trim"
        
    if len(trimmed.encode('utf-8')) > max_bytes:
        return False, f"Too long: {len(trimmed.encode('utf-8'))} > {max_bytes}"
        
    # Control character check (simplified)
    if any(ord(c) < 32 and c not in '\t\n\r' for c in trimmed):
        return False, "Contains control characters"
        
    return True, "Valid"

def validate_identifier(identifier):
    """Simulate isValidIdentifier()"""
    if not identifier:
        return False, "Empty identifier"
        
    trimmed = identifier.strip()
    if len(trimmed.encode('utf-8')) > MAX_IDENTIFIER_BYTES:
        return False, f"Too long: {len(trimmed.encode('utf-8'))}"
        
    if trimmed.startswith('-') or trimmed.endswith('-'):
        return False, "Starts or ends with dash"
        
    return True, "Valid"

def validate_os_version(version):
    """Simulate PackageSystemVersion validation"""
    if not isinstance(version, str):
        return False, "Not string"
        
    # Basic version format check
    parts = version.split('.')
    if len(parts) < 2:
        return False, "Need at least major.minor"
        
    try:
        for part in parts:
            int(part)
    except ValueError:
        return False, "Non-numeric version parts"
        
    return True, "Valid"

def validate_repository(data):
    """Main validation function"""
    print("🔍 Validating Repository JSON...")
    
    # File size check
    json_str = json.dumps(data)
    size = len(json_str.encode('utf-8'))
    print(f"📏 File size: {size} bytes (max: {MAX_MANIFEST_BYTES})")
    if size > MAX_MANIFEST_BYTES:
        return False, "File too large"
    
    # Schema version
    if data.get('schemaVersion') != 1:
        return False, f"Invalid schema version: {data.get('schemaVersion')}"
    print("✅ Schema version: 1")
    
    # Repository level validation
    valid, msg = validate_identifier(data.get('identifier', ''))
    if not valid:
        return False, f"Invalid repository identifier: {msg}"
    print(f"✅ Repository identifier: {data['identifier']}")
    
    valid, msg = validate_text(data.get('name', ''), MAX_NAME_BYTES, required=True)
    if not valid:
        return False, f"Invalid repository name: {msg}"
    print(f"✅ Repository name: {data['name']}")
    
    valid, msg = validate_text(data.get('description'), MAX_DESCRIPTION_BYTES, required=False)
    if not valid:
        return False, f"Invalid repository description: {msg}"
    print(f"✅ Repository description: OK")
    
    # Repository icon URL
    if data.get('icon'):
        valid, msg = validate_url(data['icon'])
        if not valid:
            return False, f"Invalid repository icon URL: {msg}"
        print(f"✅ Repository icon URL: OK")
    else:
        print("✅ Repository icon: None")
    
    # Package count
    packages = data.get('packages', [])
    if len(packages) > MAX_PACKAGE_COUNT:
        return False, f"Too many packages: {len(packages)} > {MAX_PACKAGE_COUNT}"
    print(f"✅ Package count: {len(packages)}")
    
    # Validate each package
    identifiers = set()
    for i, pkg in enumerate(packages):
        print(f"\n🔍 Validating Package {i+1}: {pkg.get('name', 'Unknown')}")
        
        # Package identifier
        pkg_id = pkg.get('identifier', '')
        valid, msg = validate_identifier(pkg_id)
        if not valid:
            return False, f"Package {i+1} invalid identifier: {msg}"
        if pkg_id in identifiers:
            return False, f"Package {i+1} duplicate identifier: {pkg_id}"
        identifiers.add(pkg_id)
        print(f"✅ Package identifier: {pkg_id}")
        
        # Required string fields
        for field, max_bytes in [
            ('name', MAX_NAME_BYTES),
            ('author', MAX_AUTHOR_BYTES), 
            ('version', 64),
            ('summary', MAX_SUMMARY_BYTES)
        ]:
            valid, msg = validate_text(pkg.get(field), max_bytes, required=True)
            if not valid:
                return False, f"Package {i+1} invalid {field}: {msg}"
            print(f"✅ Package {field}: {pkg[field]}")
        
        # Optional string fields
        for field, max_bytes in [
            ('description', MAX_DESCRIPTION_BYTES),
            ('category', 80),
            ('changelog', MAX_CHANGELOG_BYTES),
            ('publishedAt', 64),
            ('password', MAX_PASSWORD_BYTES)
        ]:
            if pkg.get(field) is not None:
                valid, msg = validate_text(pkg[field], max_bytes, required=False)
                if not valid:
                    return False, f"Package {i+1} invalid {field}: {msg}"
                print(f"✅ Package {field}: OK")
        
        # Tags validation
        tags = pkg.get('tags', [])
        if len(tags) > MAX_TAG_COUNT:
            return False, f"Package {i+1} too many tags: {len(tags)} > {MAX_TAG_COUNT}"
        for j, tag in enumerate(tags):
            valid, msg = validate_text(tag, MAX_TAG_BYTES, required=True)
            if not valid:
                return False, f"Package {i+1} tag {j+1} invalid: {msg}"
        print(f"✅ Package tags: {len(tags)} tags")
        
        # Screenshots validation
        screenshots = pkg.get('screenshots', [])
        if len(screenshots) > MAX_SCREENSHOT_COUNT:
            return False, f"Package {i+1} too many screenshots: {len(screenshots)}"
        for j, screenshot in enumerate(screenshots):
            valid, msg = validate_url(screenshot)
            if not valid:
                return False, f"Package {i+1} screenshot {j+1} invalid URL: {msg}"
        print(f"✅ Package screenshots: {len(screenshots)} screenshots")
        
        # URL validations
        for url_field in ['icon', 'banner']:
            if pkg.get(url_field):
                valid, msg = validate_url(pkg[url_field])
                if not valid:
                    return False, f"Package {i+1} invalid {url_field} URL: {msg}"
                print(f"✅ Package {url_field} URL: OK")
        
        # Download URL (required)
        download_url = pkg.get('download')
        if not download_url:
            return False, f"Package {i+1} missing download URL"
        valid, msg = validate_url(download_url)
        if not valid:
            return False, f"Package {i+1} invalid download URL: {msg}"
        print(f"✅ Package download URL: {download_url}")
        
        # Size validation
        size = pkg.get('size')
        if size is not None and (not isinstance(size, int) or size <= 0):
            return False, f"Package {i+1} invalid size: {size}"
        print(f"✅ Package size: {size}")
        
        # Supported OS validation
        supported_os = pkg.get('supportedOS', [])
        if not supported_os:
            return False, f"Package {i+1} missing supportedOS"
        for j, os_range in enumerate(supported_os):
            min_ver = os_range.get('minimum')
            max_ver = os_range.get('maximum')
            
            valid, msg = validate_os_version(min_ver)
            if not valid:
                return False, f"Package {i+1} OS range {j+1} invalid minimum: {msg}"
            
            valid, msg = validate_os_version(max_ver)
            if not valid:
                return False, f"Package {i+1} OS range {j+1} invalid maximum: {msg}"
                
            print(f"✅ Package OS range {j+1}: {min_ver} - {max_ver}")
    
    print("\n🎉 All validations passed!")
    return True, "Valid"

def main():
    print("🚀 TIMO MOD Repository Validation Debug")
    print("=" * 50)
    
    # Test current repository
    repo_url = "https://raw.githubusercontent.com/k3ndzy/TIMOMOD-repo/main/repositories/official/repo-1788887006.json"
    print(f"📡 Fetching: {repo_url}")
    
    try:
        response = requests.get(repo_url, timeout=10)
        response.raise_for_status()
        
        print(f"📦 Downloaded: {len(response.content)} bytes")
        
        data = response.json()
        
        valid, msg = validate_repository(data)
        if valid:
            print("\n✅ REPOSITORY IS VALID!")
            print("The issue is likely in the Swift app code or network layer.")
        else:
            print(f"\n❌ REPOSITORY VALIDATION FAILED: {msg}")
            print("This explains the app error!")
            
    except Exception as e:
        print(f"❌ Error fetching/parsing repository: {e}")

if __name__ == "__main__":
    main()