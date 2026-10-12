#!/usr/bin/env python3
"""NitroFan: controle de ventoinhas via driver linuwu_sense."""
import glob
import os
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

NITRO = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/nitro_sense"
FAN_SPEED = os.path.join(NITRO, "fan_speed")
MIN_MANUAL = 30        # abaixo disso o driver aceita, mas é arriscado
DANGER_TEMP = 95       # °C: volta ao automático se passar disso em modo manual


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def hwmon_by_name(name):
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        if read(h + "/name") == name:
            return h
    return None


ACER = hwmon_by_name("acer")
CORETEMP = hwmon_by_name("coretemp")


def write_fan(cpu, gpu):
    """cpu/gpu em %; 0,0 = automático."""
    with open(FAN_SPEED, "w") as f:
        f.write(f"{cpu},{gpu}")


def milli(path):
    v = read(path)
    return int(v) / 1000 if v and v.lstrip("-").isdigit() else None


def rpm(n):
    v = read(f"{ACER}/fan{n}_input") if ACER else None
    return int(v) if v and v.isdigit() else None


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="NitroFan")
        self.set_default_size(460, -1)
        self.mode = "auto"
        self.gpu_temp = None
        self.updating = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(box)
        self.set_content(self.toasts)

        page = Adw.PreferencesPage()
        box.append(page)

        # Leituras
        g = Adw.PreferencesGroup(title="Monitor")
        page.add(g)
        self.cpu_row = Adw.ActionRow(title="CPU")
        self.gpu_row = Adw.ActionRow(title="GPU")
        for r in (self.cpu_row, self.gpu_row):
            r.add_css_class("property")
            g.add(r)

        # Modo
        g = Adw.PreferencesGroup(title="Ventoinhas")
        page.add(g)
        self.btn_auto = Gtk.ToggleButton(label="Automático")
        self.btn_max = Gtk.ToggleButton(label="Máximo", group=self.btn_auto)
        self.btn_man = Gtk.ToggleButton(label="Manual", group=self.btn_auto)
        mode_box = Gtk.Box(spacing=0, halign=Gtk.Align.CENTER,
                           margin_top=6, margin_bottom=6)
        mode_box.add_css_class("linked")
        for b, m in ((self.btn_auto, "auto"), (self.btn_max, "max"),
                     (self.btn_man, "manual")):
            b.connect("toggled", self.on_mode, m)
            mode_box.append(b)
        row = Adw.PreferencesRow()
        row.set_child(mode_box)
        g.add(row)

        self.sc_cpu = self.make_scale(g, "Ventoinha CPU")
        self.sc_gpu = self.make_scale(g, "Ventoinha GPU")
        self.ready = False
        self.btn_auto.set_active(True)
        self.ready = True
        self.refresh_sensitivity()

        self.status = Gtk.Label(wrap=True, margin_top=6, margin_bottom=12,
                                margin_start=12, margin_end=12)
        self.status.add_css_class("dim-label")
        box.append(self.status)

        if not os.path.exists(FAN_SPEED):
            self.status.set_text("Driver linuwu_sense não carregado.")
            page.set_sensitive(False)
        elif not os.access(FAN_SPEED, os.W_OK):
            self.status.set_text("Sem permissão em fan_speed: entre no grupo "
                                 "linuwu_sense e faça login de novo.")

        self.tick()
        GLib.timeout_add_seconds(2, self.tick)
        GLib.timeout_add_seconds(3, self.poll_gpu)
        self.poll_gpu()
        self.connect("close-request", self.on_close)

    def make_scale(self, group, title):
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                                      MIN_MANUAL, 100, 5)
        sc.set_value(60)
        sc.set_draw_value(True)
        sc.set_hexpand(True)
        sc.set_value_pos(Gtk.PositionType.RIGHT)
        sc.set_size_request(200, -1)
        sc.connect("value-changed", self.on_scale)
        row = Adw.ActionRow(title=title)
        row.add_suffix(sc)
        group.add(row)
        return sc

    # --- ações ---
    def apply(self, cpu, gpu, label):
        try:
            write_fan(cpu, gpu)
            self.status.set_text(label)
        except OSError as e:
            self.toasts.add_toast(Adw.Toast.new(f"Falha ao escrever: {e}"))

    def refresh_sensitivity(self):
        manual = self.mode == "manual"
        self.sc_cpu.set_sensitive(manual)
        self.sc_gpu.set_sensitive(manual)

    def on_mode(self, btn, mode):
        if not btn.get_active() or not self.ready:
            return
        self.mode = mode
        self.refresh_sensitivity()
        if mode == "auto":
            self.apply(0, 0, "Controle automático da BIOS.")
        elif mode == "max":
            self.apply(100, 100, "Ventoinhas a 100%.")
        else:
            self.on_scale(None)

    def on_scale(self, _):
        if self.mode != "manual":
            return
        c, g = int(self.sc_cpu.get_value()), int(self.sc_gpu.get_value())
        self.apply(c, g, f"Manual: CPU {c}% / GPU {g}%.")

    def on_close(self, *_):
        # Nunca deixar o notebook preso em modo manual ao fechar o app.
        if self.mode != "auto" and os.access(FAN_SPEED, os.W_OK):
            try:
                write_fan(0, 0)
            except OSError:
                pass
        return False

    # --- leituras ---
    def poll_gpu(self):
        def work():
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=temperature.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3).stdout.strip()
                self.gpu_temp = float(out.splitlines()[0])
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                self.gpu_temp = None
        threading.Thread(target=work, daemon=True).start()
        return True

    def tick(self):
        t_cpu = milli(CORETEMP + "/temp1_input") if CORETEMP else None
        fmt = lambda t, r: (f"{t:.0f} °C" if t is not None else "—") + \
            "   ·   " + (f"{r} RPM" if r is not None else "— RPM")
        self.cpu_row.set_subtitle(fmt(t_cpu, rpm(1)))
        self.gpu_row.set_subtitle(fmt(self.gpu_temp, rpm(2)))
        hot = max([t for t in (t_cpu, self.gpu_temp) if t is not None],
                  default=0)
        if self.mode != "auto" and hot >= DANGER_TEMP:
            self.btn_auto.set_active(True)
            self.toasts.add_toast(Adw.Toast.new(
                f"{hot:.0f} °C: voltando ao modo automático."))
        return True


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.nitrofan")

    def do_startup(self):
        Adw.Application.do_startup(self)
        # libadwaita ignores/conflicts with this legacy GTK setting; follow
        # the system color scheme through AdwStyleManager instead.
        Gtk.Settings.get_default().set_property(
            "gtk-application-prefer-dark-theme", False)
        Gtk.Window.set_default_icon_name("nitrofan")

    def do_activate(self):
        (self.props.active_window or Window(self)).present()


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
