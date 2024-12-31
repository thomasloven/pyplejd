# Pyplejd

Python package for communicating with and controlling [Plejd](https://plejd.com) devices with [Home Assistant](https://home-assistant.io)

---

Contributors not listed in git history - in no particular order:

- [@astrandb](https://github.com/astrandb)
- [@bnordli](https://github.com/bnordli)
- [@oyvindwe](https://github.com/oyvindwe)
- [@NewsGuyTor](https://github.com/NewsGuyTor)

---

Notes for my memory:

```
> python setup.py sdist
> pip install twine
> twine upload -r pypi --config-file .pypirc dist/\*
```

# Traits:

DWN: powerable, groupable, dimmable
0000 1111: DWN-01

0100 1000: Groupable
0001 0000: Coverable
0100 0000: CoverTiltable

0001 1000: Cover
0101 1000: Cover + Tilt

# JAL-01

Down command: 16 0110 0420 030827 01 0000
16 0110 0420 030827 010000
16 0110 0420 030807 00
Up command: 16 0110 0420 030827 01 ffff
49 %: 16 0110 0420 030827 017f7f
Stop command: 16 0110 0420 030807 00

Angle up: 16 0110 0420 03088f0900
Angle down: 16 0110 0420 03088f09a6
Angle mid: 16 0110 0420 03088f09e2

0 _: 16 0110 0420 03088f 0900
16 0110 0098 000000 00
-15_: 16 0110 0420 03088f 09f1
16 0110 0098 000000 3c
+15*: 16 0110 0420 03088f 090f
16 0110 0098 008000 02
-30*: 16 0110 0420 03088f 09e2
16 0110 0098 000000 39
+30*: 16 0110 0420 03088f 091e
16 0110 0098 008000 05
-45*: 16 0110 0420 03088f 09d3
16 0110 0098 000000 37
+45*: 16 0110 0420 03088f 092d
16 0110 0098 008000 09
-60*: 16 0110 0420 03088f 09c4
16 0110 0098 000000 33
+60*: 16 0110 0420 03088f093c
16 0110 0098 008000 0b
-75*: 16 0110 0420 03088f 09b5
16 0110 0098 000000 30
+75*: 16 0110 0420 03088f 094b
16 0110 0098 008000 0e
-90*: 16 0110 0420 03088f 09a6
16 0110 0098 000000 2e
+90\*: 16 0110 0420 03088f 095a
16 0110 0098 008000 12

6 bitar signed int

0 15 30 45 60 75 90
00 02 05 09 0b 0e 12
0 2 5 9 11 14 18

00 3c 39 37 33 30 2e
0 -3 -6 -8 -12 -15 -17

Going up: 160110009800ca4a 12
Going down: 1601100098000000 2e

      32767
      32639

      15291
      15163

Holding up: 16 0110 0420 278300 3c3f04000000000301
Releasing up: 16 0110 0420 07003f 04000000000301

Holding down: 16 0110 0420 270300 3c3f04000000000301
Releasing down: 16 0110 0420 07003f 04000000000301
Holding down looks like a luminosity/motion command?

Motion: 13 0110 0420 03031f 0700b30f08461600a8
