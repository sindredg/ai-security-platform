"""Print the custom resource definitions from Argo's namespace install.

The release's file is one YAML stream. Its definitions go to the cluster as
released. The rest of it, the controller and the server, is not applied:
argo.yaml holds the controller, adapted. Prints each name it keeps to
standard error. Standard library only.

Usage: crds.py namespace-install.yaml | kubectl apply --server-side -f -
"""

import re
import sys
from pathlib import Path

KIND = re.compile(r"^kind: CustomResourceDefinition$", re.MULTILINE)
NAME = re.compile(r"^  name: (\S+)$", re.MULTILINE)


def main(path):
    text = Path(path).read_text(encoding="utf-8")
    kept = [d for d in re.split(r"^---$", text, flags=re.MULTILINE) if KIND.search(d)]
    if not kept:
        print("no custom resource definitions found", file=sys.stderr)
        return 1
    for doc in kept:
        print(NAME.search(doc).group(1), file=sys.stderr)
        sys.stdout.write("---\n" + doc.strip("\n") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
