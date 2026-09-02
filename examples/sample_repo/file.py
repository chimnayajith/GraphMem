"""Matches the example in the parser task description:

file.py
├── ClassA
│    ├── method1()
│    └── method2()
│
└── function1()
"""

from pkg.sub.helpers import normalize
import os


class ClassA:
    def method1(self, value):
        return normalize(value)

    def method2(self):
        return os.getcwd()


def function1():
    return ClassA().method1("hi")
