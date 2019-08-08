#!/usr/bin/env bash

# Remove old dist
trash dist  # sudo apt install trash-cli

# Build
python setup.py sdist bdist_wheel

# Check files
tar tzf dist/botleague-helpers-*.gz

# Upload to test PyPi [optional]
#twine upload --repository-url https://test.pypi.org/legacy/ dist/*

# Upload to PyPi
twine upload dist/*