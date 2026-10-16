#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
cc -std=c11 -Wall -Wextra -Werror src/calc.c -lm -o build/calc
check() { expected=$1; shift; actual=$(build/calc "$@") || { echo "FAIL: $*"; exit 1; }; [ "$actual" = "$expected" ] || { echo "FAIL: $*: got $actual expected $expected"; exit 1; }; }
check 1024 '2^10'
check 14 '2+3*4'
check 20 '(2+3)*4'
check -4 '-2^2'
check 9 'sqrt(81)'
check 8 'pow(2,3)'
check 3 'abs(-3)'
check 5 'floor(5.8)'
check 6 'ceil(5.2)'
check 1 'sin(0)+cos(0)'
check 6 '2%3+4'
if build/calc '1/0' 2>/dev/null; then echo 'FAIL: divide by zero'; exit 1; fi
if build/calc '2+' 2>/dev/null; then echo 'FAIL: malformed expression'; exit 1; fi
printf 'ALL PASS\n'
