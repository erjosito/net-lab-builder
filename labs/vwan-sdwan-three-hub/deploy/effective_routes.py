"""Use the CLI's bounded ARM long-running-operation poller, not POST stdout."""
import time


def resource_id(subscription, group, site, connection=True):
    hub = f"/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.Network/virtualHubs/hub-{site}"
    return (f"{hub}/hubVirtualNetworkConnections/conn-spoke-{site}" if connection
            else f"{hub}/hubRouteTables/defaultRouteTable")


def arguments(subscription, group, site, connection=True, firewall_id=None):
    if firewall_id is not None and not firewall_id.startswith("/subscriptions/"):
        raise ValueError("Firewall evidence requires an ARM resource ID")
    return ["network", "vhub", "get-effective-routes", "-g", group,
            "-n", f"hub-{site}", "--resource-id",
            firewall_id or resource_id(subscription, group, site, connection),
            "--resource-type", "AzureFirewall" if firewall_id else
            "HubVirtualNetworkConnection" if connection else "RouteTable"]


def collect(az, subscription, group, site, label, connection=True, firewall_id=None):
    value = az(arguments(subscription, group, site, connection, firewall_id), label)
    if not isinstance(value, dict) or not isinstance(value.get("value"), list):
        raise RuntimeError(f"{label}: missing completed effectiveRoutes response")
    return value


def two_snapshots(capture, wait=time.sleep, clock=time.monotonic, interval=120):
    first = capture(1)
    completed = clock()
    wait(max(0, completed + interval - clock()))
    return first, capture(2)
