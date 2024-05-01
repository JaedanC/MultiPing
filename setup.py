from py2exe import freeze

# https://github.com/py2exe/py2exe/blob/master/docs/py2exe.freeze.md

freeze(
    console=[{"script": "mping.py"}],
    options={
        "packages": ["tabulate"],
        "bundle_files": 1
    }
)
