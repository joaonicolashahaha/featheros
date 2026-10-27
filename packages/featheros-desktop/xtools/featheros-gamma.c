/*
 * featheros-gamma: Night Light ("Luz noturna"). Sets every monitor's gamma
 * ramp to a colour temperature and exits; nothing stays running.
 *
 *   featheros-gamma 4000    warm (Night Light on)
 *   featheros-gamma 6500    neutral (off)
 *
 * The temperature -> RGB curve is Tanner Helland's fit of the black-body
 * colours, scaled so that 6500 K is exactly white (an identity ramp).
 *
 *   cc -O2 -o featheros-gamma featheros-gamma.c -lX11 -lXrandr -lm
 */
#include <X11/Xlib.h>
#include <X11/extensions/Xrandr.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static void blackbody(double kelvin, double rgb[3])
{
    double t = kelvin / 100.0;

    rgb[0] = t <= 66 ? 255 : 329.698727446 * pow(t - 60, -0.1332047592);
    rgb[1] = t <= 66 ? 99.4708025861 * log(t) - 161.1195681661
                     : 288.1221695283 * pow(t - 60, -0.0755148492);
    if (t >= 66)
        rgb[2] = 255;
    else if (t <= 19)
        rgb[2] = 0;
    else
        rgb[2] = 138.5177312231 * log(t - 10) - 305.0447927307;
}

int main(int argc, char **argv)
{
    Display *dpy;
    XRRScreenResources *res;
    double kelvin = argc == 2 ? atof(argv[1]) : 0, rgb[3], white[3];
    int c, i;

    if (kelvin < 1000 || kelvin > 10000) {
        fprintf(stderr, "usage: featheros-gamma KELVIN  (1000-10000; 6500 = neutral)\n");
        return 2;
    }
    blackbody(kelvin, rgb);
    blackbody(6500, white);
    for (i = 0; i < 3; i++) {
        rgb[i] /= white[i];
        if (rgb[i] > 1)
            rgb[i] = 1;
        if (rgb[i] < 0)
            rgb[i] = 0;
    }

    dpy = XOpenDisplay(NULL);
    if (!dpy)
        return 1;
    res = XRRGetScreenResourcesCurrent(dpy, DefaultRootWindow(dpy));
    if (!res)
        return 1;
    for (c = 0; c < res->ncrtc; c++) {
        int size = XRRGetCrtcGammaSize(dpy, res->crtcs[c]);
        XRRCrtcGamma *ramp;

        if (size < 2)
            continue; /* no gamma support (some virtual GPUs) */
        ramp = XRRAllocGamma(size);
        for (i = 0; i < size; i++) {
            double v = 65535.0 * i / (size - 1);
            ramp->red[i] = (unsigned short)(v * rgb[0]);
            ramp->green[i] = (unsigned short)(v * rgb[1]);
            ramp->blue[i] = (unsigned short)(v * rgb[2]);
        }
        XRRSetCrtcGamma(dpy, res->crtcs[c], ramp);
        XRRFreeGamma(ramp);
    }
    XRRFreeScreenResources(res);
    XCloseDisplay(dpy);
    return 0;
}
