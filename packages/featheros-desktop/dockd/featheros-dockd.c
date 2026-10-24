/*
 * featheros-dockd: "intelligent hide" for the FeatherOS dock.
 *
 * The dock (the tint2 panel named "featheros-dock", autohide = 1) stays
 * visible while no window overlaps it and hides when one does; touching the
 * bottom edge still shows it, as with plain autohide. tint2 has no such
 * mode, so this helper drives tint2's own autohide by sending the dock the
 * Enter/Leave events it would get from the mouse.
 *
 * Event-driven (no polling): it wakes up only when windows are mapped,
 * moved, resized or minimized, or when the pointer leaves the dock.
 * Started by featheros-panels; exits with the X session.
 *
 *   cc -O2 -o featheros-dockd featheros-dockd.c -lX11
 */
#include <X11/Xatom.h>
#include <X11/Xlib.h>
#include <string.h>

#define DOCK_NAME "featheros-dock"
#define BAR_NAME "featheros-bar"
#define HIDDEN_MAX 8      /* a hidden tint2 panel is an autohide_height strip */
#define DEFAULT_HEIGHT 72 /* dock height until it has been seen shown */

static Display *dpy;
static Window root, dock, dock_top, bar;
static Atom a_client_list, a_wm_type, a_type_dock;
static int sx, sy, sw, sh, have_shown; /* dock rectangle when shown */
static int last_sent;                  /* EnterNotify/LeaveNotify/0 */

/* Windows come and go: ignore BadWindow & co instead of exiting. */
static int ignore_errors(Display *d, XErrorEvent *e)
{
    (void)d;
    (void)e;
    return 0;
}

static int has_name(Window w, const char *name)
{
    char *n = NULL;
    int r = 0;
    if (XFetchName(dpy, w, &n) && n) {
        r = strcmp(n, name) == 0;
        XFree(n);
    }
    return r;
}

static Window find_named(Window w, const char *name, int depth)
{
    Window r, p, *kids = NULL, found = None;
    unsigned int n, i;
    if (has_name(w, name))
        return w;
    if (depth == 0 || !XQueryTree(dpy, w, &r, &p, &kids, &n))
        return None;
    for (i = 0; i < n && !found; i++)
        found = find_named(kids[i], name, depth - 1);
    if (kids)
        XFree(kids);
    return found;
}

/* The direct child of the root window that contains w (its WM frame). */
static Window top_level(Window w)
{
    Window r, p, *kids = NULL;
    unsigned int n;
    while (w != None && XQueryTree(dpy, w, &r, &p, &kids, &n)) {
        if (kids)
            XFree(kids);
        if (p == r)
            return w;
        w = p;
    }
    return None;
}

static int locate(void)
{
    dock = find_named(root, DOCK_NAME, 3);
    bar = find_named(root, BAR_NAME, 3);
    dock_top = top_level(dock);
    have_shown = last_sent = 0;
    if (!dock_top)
        return 0;
    /* Pointer leaving the dock, and the dock's own resizes (hide/show). */
    XSelectInput(dpy, dock, LeaveWindowMask | StructureNotifyMask);
    return 1;
}

static int is_dock_type(Window w)
{
    Atom type, *v = NULL;
    int fmt, r = 0;
    unsigned long n, left;
    if (XGetWindowProperty(dpy, w, a_wm_type, 0, 8, False, XA_ATOM, &type,
                           &fmt, &n, &left, (unsigned char **)&v) == Success && v) {
        for (unsigned long i = 0; i < n; i++)
            r |= v[i] == a_type_dock;
        XFree(v);
    }
    return r;
}

/* Does any visible application window overlap the dock's shown area? */
static int overlapped(void)
{
    Atom type;
    int fmt, hit = 0;
    unsigned long n, left;
    Window *clients = NULL;
    XWindowAttributes a;

    if (XGetWindowProperty(dpy, root, a_client_list, 0, 1024, False, XA_WINDOW,
                           &type, &fmt, &n, &left,
                           (unsigned char **)&clients) != Success || !clients)
        return 0;
    for (unsigned long i = 0; i < n && !hit; i++) {
        Window c = clients[i], t;
        if (c == dock || c == bar || is_dock_type(c))
            continue;
        t = top_level(c);
        /* Minimized windows have an unmapped frame. */
        if (!t || !XGetWindowAttributes(dpy, t, &a) || a.map_state != IsViewable)
            continue;
        hit = a.x < sx + sw && a.x + a.width + 2 * a.border_width > sx &&
              a.y < sy + sh && a.y + a.height + 2 * a.border_width > sy;
    }
    XFree(clients);
    return hit;
}

static int pointer_on_dock(void)
{
    Window r, c;
    int x, y, wx, wy;
    unsigned int m;
    if (!XQueryPointer(dpy, root, &r, &c, &x, &y, &wx, &wy, &m))
        return 0;
    return x >= sx && x < sx + sw && y >= sy && y < sy + sh;
}

static void send_crossing(int type)
{
    XEvent e;
    memset(&e, 0, sizeof e);
    e.xcrossing.type = type;
    e.xcrossing.display = dpy;
    e.xcrossing.window = dock;
    e.xcrossing.root = root;
    e.xcrossing.time = CurrentTime;
    e.xcrossing.mode = NotifyNormal;
    e.xcrossing.detail = NotifyNonlinear;
    e.xcrossing.same_screen = True;
    XSendEvent(dpy, dock, False,
               type == EnterNotify ? EnterWindowMask : LeaveWindowMask, &e);
    XFlush(dpy);
    last_sent = type;
}

/* pointer_left: the real pointer just left the dock (tint2 will start its
 * hide timer; answer with an Enter at once if the dock should stay). */
static void evaluate(int pointer_left)
{
    XWindowAttributes a;
    int hidden, want_shown;

    if (!dock_top || !XGetWindowAttributes(dpy, dock_top, &a)) {
        if (!locate() || !XGetWindowAttributes(dpy, dock_top, &a))
            return;
    }
    hidden = a.height <= HIDDEN_MAX;
    if (!hidden) {
        sx = a.x, sy = a.y, sw = a.width, sh = a.height, have_shown = 1;
    } else if (!have_shown) {
        sw = a.width, sh = DEFAULT_HEIGHT;
        sx = a.x, sy = a.y + a.height - sh;
    }
    want_shown = !overlapped();

    if (want_shown && (pointer_left || (hidden && last_sent != EnterNotify)))
        send_crossing(EnterNotify);
    else if (!want_shown && !hidden && last_sent != LeaveNotify && !pointer_on_dock())
        send_crossing(LeaveNotify);
    else if (want_shown == hidden)
        ; /* waiting for tint2's show/hide timer */
    else
        last_sent = 0; /* state reached: allow the next action */
}

int main(void)
{
    XEvent ev;

    if (!(dpy = XOpenDisplay(NULL)))
        return 1;
    XSetErrorHandler(ignore_errors);
    root = DefaultRootWindow(dpy);
    a_client_list = XInternAtom(dpy, "_NET_CLIENT_LIST", False);
    a_wm_type = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE", False);
    a_type_dock = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DOCK", False);

    /* Top-level windows mapped/unmapped/moved/resized, client list changes. */
    XSelectInput(dpy, root, SubstructureNotifyMask | PropertyChangeMask);
    locate();
    evaluate(0);

    for (;;) {
        XNextEvent(dpy, &ev);
        if (ev.type == LeaveNotify && ev.xcrossing.window == dock &&
            !ev.xcrossing.send_event && ev.xcrossing.mode == NotifyNormal)
            evaluate(1);
        else if (ev.type == PropertyNotify && ev.xproperty.atom != a_client_list)
            continue;
        else
            evaluate(0);
    }
}
