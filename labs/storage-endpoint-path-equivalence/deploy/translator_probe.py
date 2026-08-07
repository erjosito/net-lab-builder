#!/usr/bin/env python3
import argparse
import ipaddress
import json
import socket
import urllib.parse
import urllib.request


def token():
    resource = urllib.parse.quote("https://cognitiveservices.azure.com/", safe="")
    url = (
        "http://169.254.169.254/metadata/identity/oauth2/token"
        f"?api-version=2018-02-01&resource={resource}"
    )
    request = urllib.request.Request(url, headers={"Metadata": "true"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["access_token"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--region", default="swedencentral")
    parser.add_argument("--expect", choices=("public", "private"), required=True)
    args = parser.parse_args()

    host = urllib.parse.urlparse(args.endpoint).hostname
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    private = [address for address in addresses if ipaddress.ip_address(address).is_private]
    observed = "private" if private else "public"
    if observed != args.expect:
        raise SystemExit(f"DNS mode mismatch: expected {args.expect}, observed {observed}")
    if args.expect == "private" and "10.61.2.4" not in addresses:
        raise SystemExit("Private DNS did not resolve the approved PE address")

    body = json.dumps([{"Text": "Network path probe."}]).encode()
    url = f"{args.endpoint.rstrip('/')}/translator/text/v3.0/translate?api-version=3.0&to=fr"
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json; charset=UTF-8",
            "Ocp-Apim-Subscription-Region": args.region,
            "X-ClientTraceId": "sepath-translator-probe",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise SystemExit(f"Translator returned HTTP {response.status}")
        response.read()
        print(json.dumps({"dnsMode": observed, "httpStatus": response.status, "validated": True}))


if __name__ == "__main__":
    main()
