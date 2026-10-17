# Eagle Eye camera source integration

The Windy Webcams source boundary and object-camera integration are adapted from [Ryan-Milton/Eagle-Eye](https://github.com/Ryan-Milton/Eagle-Eye), commit `8e393035fd203398ce235de640310c53451f0dcf`, specifically `src/lib/camera-client.ts` and the camera proxy in `server/index.ts`. The integration uses the documented Windy V3 string-valued player URLs; it distinguishes live players from timelapse replay. Other Eagle Eye feeds are not enabled by this change.

## Eagle Eye license

MIT License

Copyright (c) 2026 Ryan Milton

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
