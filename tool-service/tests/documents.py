"""Evidence documents that pass their schemas, one per kind, for the tests to
store and to break."""

COLLECTED = "2026-10-25T08:00:00Z"


def synthetic(reference, token):
    return {
        "reference": reference,
        "collected": COLLECTED,
        "token": token,
        "contract_object_types": ["dcim.device", "ipam.prefix"],
        "granted_object_types": ["dcim.device", "ipam.prefix", "tenancy.contact"],
        "write_access": False,
    }


def contract(job):
    return {
        "reference": "ev-0001",
        "job": job,
        "collected": COLLECTED,
        "accounts": ["inventory-reader", "inventory-reader-control"],
        "viewpoint": "10.50.0.36",
        "grants": [
            {
                "object_type": "dcim.device",
                "action": "view",
                "constraints": {"tenant__slug": "tenant-a"},
            }
        ],
        "reads": [
            {
                "path": "/api/dcim/devices/",
                "key": "name",
                "fields": ["id", "name", "tenant"],
                "records": ["a-fw-01", "a-sw-01"],
            },
            {
                "path": "/api/ipam/ip-addresses/",
                "key": "address",
                "fields": ["id", "address"],
                "records": ["172.16.1.1/24"],
            },
        ],
        "denials": [
            {"method": "GET", "path": "/api/dcim/sites/", "status": 403},
            {"method": "POST", "path": "/api/dcim/devices/", "status": 403},
        ],
    }


def configured(job):
    return {
        "reference": "ev-0002",
        "job": job,
        "collected": COLLECTED,
        "accounts": {
            "inventory-reader": {
                "permissions": [
                    {
                        "id": 3,
                        "object_types": ["dcim.device", "ipam.ipaddress"],
                        "actions": ["view"],
                        "constraints": {"tenant__slug": "tenant-a"},
                        "via": "user",
                    },
                    {
                        "id": 4,
                        "object_types": ["dcim.device"],
                        "actions": ["view"],
                        "constraints": None,
                        "via": "group",
                    },
                ]
            },
            "inventory-reader-control": {"permissions": []},
        },
    }


def observed(job, records=("a-fw-01", "a-sw-01", "b-fw-01")):
    return {
        "reference": "ev-0003",
        "job": job,
        "collected": COLLECTED,
        "accounts": {
            "inventory-reader": {
                "reads": {"/api/dcim/devices/": list(records)},
                "denials": [
                    {"method": "POST", "path": "/api/dcim/devices/", "status": 403}
                ],
            }
        },
    }
