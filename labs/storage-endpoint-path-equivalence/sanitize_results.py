#!/usr/bin/env python3
import argparse
import ipaddress
import re
from pathlib import Path


GUID = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
LAB_STORAGE = re.compile(r"\bstsepath[a-z0-9]+\b", re.IGNORECASE)


def sanitize(text):
    text = JWT.sub("<TOKEN>", text)
    text = GUID.sub("<GUID>", text)
    text = text.replace("aisepath0805175837", "<TRANSLATOR_ACCOUNT>")
    text = text.replace("rg-storage-sepath-0805175837", "<RESOURCE_GROUP>")
    text = LAB_STORAGE.sub("<FLOW_STORAGE>", text)

    def replace_ip(match):
        value = match.group(0)
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return value
        if address.is_private or address.is_loopback or value in ("0.0.0.0", "168.63.129.16", "169.254.169.254"):
            return value
        return "<PUBLIC_IP>"

    return IPV4.sub(replace_ip, text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(sanitize(args.source.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
