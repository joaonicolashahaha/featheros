/*
 * featheros-idle: print how long the keyboard and mouse have been idle, in
 * milliseconds. Run once a minute by /usr/lib/featheros/sessiond (screen
 * time, automatic suspend). Exits with 1 when there is no X display, which
 * tells sessiond that the session has ended.
 *
 * The X server may reset its idle time when DPMS switches the monitor off;
 * like xprintidle, add the DPMS timeout back while the monitor is off.
 *
 *   cc -O2 -o featheros-idle featheros-idle.c -lX11 -lXext -lXss
 */
#include <X11/Xlib.h>
#include <X11/extensions/dpms.h>
#include <X11/extensions/scrnsaver.h>
#include <stdio.h>

int main(void)
{
    Display *dpy = XOpenDisplay(NULL);
    XScreenSaverInfo *info;
    unsigned long idle, timeout = 0;
    int ev, err;
    CARD16 standby, suspend, off, level;
    BOOL enabled;

    if (!dpy || !XScreenSaverQueryExtension(dpy, &ev, &err))
        return 1;
    info = XScreenSaverAllocInfo();
    if (!info || !XScreenSaverQueryInfo(dpy, DefaultRootWindow(dpy), info))
        return 1;
    idle = info->idle;

    if (DPMSQueryExtension(dpy, &ev, &err) && DPMSCapable(dpy) &&
        DPMSInfo(dpy, &level, &enabled) && enabled &&
        DPMSGetTimeouts(dpy, &standby, &suspend, &off)) {
        if (level == DPMSModeStandby)
            timeout = standby;
        else if (level == DPMSModeSuspend)
            timeout = suspend;
        else if (level == DPMSModeOff)
            timeout = off;
        if (idle < timeout * 1000UL)
            idle += timeout * 1000UL;
    }

    printf("%lu\n", idle);
    XFree(info);
    XCloseDisplay(dpy);
    return 0;
}
