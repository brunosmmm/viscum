#!/bin/bash

#run flake8
echo "Running flake8"
flake8 viscum

#run rests
echo "Running tests"
python $(which nosetests) --with-coverage --cover-package=viscum tests/test_args.py
