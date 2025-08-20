#! /bin/bash

isort  $(find . -name '*.py' )  ; black  $(find .  -name '*.py' ) 
