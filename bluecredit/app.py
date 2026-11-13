"""BlueCredit desktop app (PySide6 / Qt). Interfaz en español."""
from __future__ import annotations

import html
import json
import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import __version__
from .advice import ai_advice, get_key, local_advice, set_key
from .finance import LENDERS, PURPOSES, Simulation, pesos, simulate

ASSETS = (Path(getattr(sys, "_MEIPASS", "")) / "assets") if getattr(sys, "frozen", False) \
    else Path(__file__).resolve().parent.parent / "assets"
HOME = Path(os.environ.get("BLUECREDIT_HOME", Path.home() / ".bluecredit"))
SETTINGS = HOME / "settings.json"
BG, CARD, LINE, TEXT, MUTED = "#f3f7fd", "#ffffff", "#dfe7f3", "#0f172a", "#64748b"
BLUE, GREEN, AMBER, RED = "#1d5fd6", "#15803d", "#b45309", "#b91c1c"

QSS = f"""
* {{ font-family: 'Helvetica Neue', 'Segoe UI', Arial, sans-serif; color: {TEXT}; }}
QMainWindow, QWidget#root, QScrollArea, QWidget#page {{ background: {BG}; border: none; }}
QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; }}
QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#q {{ font-size: 22px; font-weight: 700; }}
QLabel#hero {{ font-size: 30px; font-weight: 800; }}
QLabel#value {{ font-size: 34px; font-weight: 800; color: {BLUE}; }}
QLabel#h2 {{ font-size: 15px; font-weight: 700; }}
QLabel#pill {{ background: #e3edfd; color: {BLUE}; border-radius: 11px; padding: 4px 12px; font-weight: 600; }}
QPushButton {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; padding: 10px 14px; text-align: left; }}
QPushButton:hover {{ border-color: {BLUE}; }}
QPushButton:checked {{ border: 2px solid {BLUE}; background: #eef4ff; }}
QPushButton#primary {{ background: {BLUE}; color: white; border: none; font-weight: 600; padding: 12px 22px; text-align: center; }}
QPushButton#primary:disabled {{ background: #9bb8ea; }}
QPushButton#ghost {{ text-align: center; }}
QLineEdit, QDoubleSpinBox {{ border: 1px solid {LINE}; border-radius: 10px; padding: 9px; background: white; font-size: 15px; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QProgressBar {{ background: #e3e9f3; border: none; border-radius: 4px; height: 8px; }}
QProgressBar::chunk {{ background: {BLUE}; border-radius: 4px; }}
QSlider::groove:horizontal {{ height: 6px; background: #dbe3ef; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {BLUE}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; border: 3px solid {BLUE}; width: 16px; margin: -7px 0; border-radius: 10px; }}
QTableWidget {{ background: white; border: 1px solid {LINE}; border-radius: 10px; gridline-color: {LINE}; }}
QHeaderView::section {{ background: #f6f9fe; color: {MUTED}; border: none; padding: 6px; font-weight: 600; }}
"""


def load_settings() -> dict:
    base = {"rates": {k: v["ea"] for k, v in LENDERS.items()}, "usury": None}
    try:
        d = json.loads(SETTINGS.read_text())
        base["rates"].update(d.get("rates", {})); base["usury"] = d.get("usury")
    except Exception:
        pass
    return base


def save_settings(s: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2))


def md_to_html(text: str) -> str:
    out = []
    for para in text.split("\n\n"):
        p = html.escape(para)
        p = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", p).replace("\n", "<br>")
        out.append(f"<p style='margin:0 0 10px 0'>{p}</p>")
    return "".join(out)


class Worker(QObject):
    done = Signal(object)

    def __init__(self, fn, *a):
        super().__init__(); self.fn, self.a = fn, a

    def run(self):
        self.done.emit(self.fn(*self.a))


class MoneyInput(QWidget):
    """Big value + slider + exact input, kept in sync."""
    changed = Signal(float)

    def __init__(self, lo, hi, step, value, hint=""):
        super().__init__()
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)
        self.lo, self.hi, self.step = lo, hi, step
        self.big = QLabel(objectName="value"); self.big.setAlignment(Qt.AlignCenter)
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(0, int((hi - lo) / step))
        ends = QHBoxLayout(); ends.addWidget(QLabel(pesos(lo), objectName="muted")); ends.addStretch()
        ends.addWidget(QLabel(pesos(hi), objectName="muted"))
        self.box = QDoubleSpinBox(decimals=0, minimum=0, maximum=hi * 10, singleStep=step, prefix="$ ")
        self.box.setGroupSeparatorShown(True)
        v.addWidget(self.big); v.addWidget(self.slider); v.addLayout(ends); v.addWidget(self.box)
        if hint:
            h = QLabel("💡 " + hint, objectName="muted"); h.setWordWrap(True); v.addWidget(h)
        self.slider.valueChanged.connect(lambda k: self.set(lo + k * step, from_slider=True))
        self.box.valueChanged.connect(lambda x: self.set(x, from_box=True))
        self.set(value)

    def set(self, x, from_slider=False, from_box=False):
        self.value = float(x)
        self.big.setText(pesos(self.value))
        if not from_slider:
            self.slider.blockSignals(True)
            self.slider.setValue(int(round((min(max(x, self.lo), self.hi) - self.lo) / self.step)))
            self.slider.blockSignals(False)
        if not from_box:
            self.box.blockSignals(True); self.box.setValue(self.value); self.box.blockSignals(False)
        self.changed.emit(self.value)


class Bar(QWidget):
    """Debt-to-income bar with the 30% and 40% marks."""
    def __init__(self, ratio, color):
        super().__init__(); self.ratio, self.color = ratio, color; self.setFixedHeight(34)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w = self.width() - 2; r = QRectF(1, 6, w, 12)
        path = QPainterPath(); path.addRoundedRect(r, 6, 6); p.fillPath(path, QColor("#e3e9f3"))
        fill = QPainterPath(); fill.addRoundedRect(QRectF(1, 6, w * min(self.ratio, 1.0), 12), 6, 6)
        p.fillPath(fill, QColor(self.color))
        p.setPen(QColor(MUTED))
        for mark in (0.30, 0.40):
            x = 1 + w * mark; p.drawLine(int(x), 2, int(x), 22)
            p.drawText(int(x) - 12, 33, f"{mark:.0%}")


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent); self.setWindowTitle("Ajustes"); self.setMinimumWidth(480)
        f = QFormLayout(self)
        f.addRow(QLabel("<b>Tasas de referencia (efectiva anual)</b>"))
        self.rates = {}
        for k, v in LENDERS.items():
            box = QDoubleSpinBox(decimals=1, maximum=200, suffix=" % E.A."); box.setValue(settings["rates"][k] * 100)
            self.rates[k] = box; f.addRow(v["name"], box)
        self.usury = QDoubleSpinBox(decimals=2, maximum=200, suffix=" % E.A."); self.usury.setSpecialValueText("Sin configurar")
        self.usury.setValue((settings["usury"] or 0) * 100)
        f.addRow("Tasa de usura vigente", self.usury)
        n = QLabel("La tasa de usura la publica la Superintendencia Financiera cada mes. Escríbela para que BlueCredit "
                   "te avise si una tasa la supera. Déjala en 0 para no usarla.", objectName="muted"); n.setWordWrap(True)
        f.addRow(n)
        f.addRow(QLabel("<b>Clave de Claude (opcional)</b>"))
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("sk-ant-…  (guardada)" if get_key() else "sk-ant-…")
        f.addRow("API key", self.key)
        k = QLabel("Con una clave, Claude escribe la explicación. Sin ella, BlueCredit la arma con tus números. "
                   "Se guarda en el llavero del sistema.", objectName="muted"); k.setWordWrap(True); f.addRow(k)
        b = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)

    def values(self, settings):
        s = dict(settings)
        s["rates"] = {k: box.value() / 100 for k, box in self.rates.items()}
        s["usury"] = self.usury.value() / 100 if self.usury.value() > 0 else None
        if self.key.text().strip():
            set_key(self.key.text())
        return s


class MainWindow(QMainWindow):
    QUESTIONS = 6

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BlueCredit · Simulador de crédito"); self.resize(980, 860)
        self.settings = load_settings()
        self.answers = {"amount": 5_000_000, "purpose": None, "months": 24, "income": 2_500_000, "existing": 0,
                        "lender": None, "ea": None}
        self.sim: Simulation | None = None
        self.advice_text, self.advice_src = "", "local"
        self._threads = []
        root = QWidget(objectName="root"); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget(); v.addWidget(self.stack)
        self._menu()
        self.show_welcome()

    def _menu(self):
        m = self.menuBar().addMenu("Archivo")
        a = QAction("Nueva simulación", self); a.setShortcut("Ctrl+N"); a.triggered.connect(self.show_welcome); m.addAction(a)
        a = QAction("Exportar PDF…", self); a.setShortcut("Ctrl+E"); a.triggered.connect(self.export_pdf); m.addAction(a)
        a = QAction("Ajustes…", self); a.setShortcut("Ctrl+,"); a.triggered.connect(self.open_settings); m.addAction(a)
        h = self.menuBar().addMenu("Ayuda")
        a = QAction("Acerca de BlueCredit", self); a.triggered.connect(self.about); h.addAction(a)

    # ---------------------------------------------------------------- screens
    def _set_page(self, w):
        while self.stack.count():
            old = self.stack.widget(0); self.stack.removeWidget(old); old.deleteLater()
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(w)
        self.stack.addWidget(sc)

    def _centered(self, inner, width=620):
        page = QWidget(objectName="page"); outer = QHBoxLayout(page); outer.addStretch()
        col = QWidget(); col.setFixedWidth(width); outer.addWidget(col); outer.addStretch()
        lay = QVBoxLayout(col); lay.setContentsMargins(0, 28, 0, 28); lay.setSpacing(14)
        inner(lay)
        return page

    def show_welcome(self):
        def build(lay):
            lay.addStretch()
            logo = QLabel(); logo.setAlignment(Qt.AlignCenter)
            if (ASSETS / "icon.png").exists():
                logo.setPixmap(QPixmap(str(ASSETS / "icon.png")).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lay.addWidget(logo)
            pill = QLabel("BlueCredit", objectName="pill"); pill.setAlignment(Qt.AlignCenter)
            row = QHBoxLayout(); row.addStretch(); row.addWidget(pill); row.addStretch(); lay.addLayout(row)
            t = QLabel("¿Estás pensando en pedir un crédito?", objectName="hero"); t.setAlignment(Qt.AlignCenter); t.setWordWrap(True)
            s = QLabel("Te ayudamos a entender exactamente cuánto pagarías y si te conviene, en lenguaje simple.")
            s.setAlignment(Qt.AlignCenter); s.setWordWrap(True); s.setStyleSheet(f"color: {MUTED}; font-size: 15px;")
            lay.addWidget(t); lay.addWidget(s)
            b = QPushButton("Empezar simulación  →", objectName="primary"); b.clicked.connect(lambda: self.show_q(1))
            row = QHBoxLayout(); row.addStretch(); row.addWidget(b); row.addStretch(); lay.addLayout(row)
            n = QLabel("Toma menos de 1 minuto · No pedimos datos personales · Todo se calcula en tu computador", objectName="muted")
            n.setAlignment(Qt.AlignCenter); lay.addWidget(n); lay.addStretch()
            f = QLabel("BlueCredit · Simulación educativa, no es una oferta de crédito. · Blue Peak AI & Finance Solutions",
                       objectName="muted"); f.setAlignment(Qt.AlignCenter); lay.addWidget(f)
        self._set_page(self._centered(build))

    def show_q(self, n):
        def build(lay):
            head = QHBoxLayout(); head.addWidget(QLabel(f"Pregunta {n} de {self.QUESTIONS}", objectName="muted"))
            head.addStretch(); head.addWidget(QLabel(f"{round(100 * n / self.QUESTIONS)}%", objectName="muted"))
            lay.addLayout(head)
            pb = QProgressBar(); pb.setRange(0, self.QUESTIONS); pb.setValue(n); pb.setTextVisible(False); pb.setFixedHeight(8)
            lay.addWidget(pb)
            card = QFrame(objectName="card"); cv = QVBoxLayout(card); cv.setContentsMargins(24, 22, 24, 22); cv.setSpacing(10)
            ok = getattr(self, f"_q{n}")(cv)
            lay.addWidget(card)
            nav = QHBoxLayout()
            back = QPushButton("←  Atrás", objectName="ghost")
            back.clicked.connect(lambda: self.show_q(n - 1) if n > 1 else self.show_welcome())
            nxt = QPushButton("Ver mi simulación  →" if n == self.QUESTIONS else "Siguiente  →", objectName="primary")
            nxt.clicked.connect(lambda: self.show_result() if n == self.QUESTIONS else self.show_q(n + 1))
            self._next = nxt; nxt.setEnabled(ok)
            nav.addWidget(back); nav.addStretch(); nav.addWidget(nxt); lay.addLayout(nav); lay.addStretch()
            f = QLabel("BlueCredit · Simulación educativa, no es una oferta de crédito.", objectName="muted")
            f.setAlignment(Qt.AlignCenter); lay.addWidget(f)
        self._set_page(self._centered(build))

    def _title(self, cv, q, sub):
        cv.addWidget(QLabel(q, objectName="q")); s = QLabel(sub, objectName="muted"); s.setWordWrap(True); cv.addWidget(s)

    def _q1(self, cv):
        self._title(cv, "¿Cuánto dinero necesitas?", "Mueve la barra o escribe el monto exacto.")
        m = MoneyInput(500_000, 50_000_000, 100_000, self.answers["amount"],
                       "La mayoría de créditos de consumo van de $1.000.000 a $20.000.000.")
        m.changed.connect(lambda x: (self.answers.__setitem__("amount", x), self._next.setEnabled(x >= 100_000)))
        cv.addWidget(m); return self.answers["amount"] >= 100_000

    def _choices(self, cv, options, key, cols=2):
        grid = QGridLayout(); grid.setSpacing(10); g = QButtonGroup(self)
        for i, (k, label) in enumerate(options):
            b = QPushButton(label); b.setCheckable(True); b.setChecked(self.answers[key] == k); b.setMinimumHeight(48)
            b.clicked.connect(lambda _=False, k=k: (self.answers.__setitem__(key, k), self._next.setEnabled(True)))
            g.addButton(b); grid.addWidget(b, i // cols, i % cols)
        cv.addLayout(grid); self._group = g
        return self.answers[key] is not None

    def _q2(self, cv):
        self._title(cv, "¿Para qué necesitas el dinero?", "Elige la opción que más se acerque. Así te damos consejos que apliquen a tu caso.")
        icons = {"negocio": "💼", "tecnologia": "📺", "vehiculo": "🚗", "vivienda": "🏠", "educacion": "🎓", "deuda": "💳", "otro": "⋯"}
        return self._choices(cv, [(k, f"{icons[k]}  {v}") for k, v in PURPOSES.items()], "purpose")

    def _q3(self, cv):
        self._title(cv, "¿En cuánto tiempo quieres pagarlo?", "El plazo cambia mucho lo que pagas al final.")
        big = QLabel(objectName="value"); big.setAlignment(Qt.AlignCenter)
        sl = QSlider(Qt.Horizontal); sl.setRange(6, 72); sl.setValue(self.answers["months"])

        def upd(m):
            self.answers["months"] = m
            big.setText(f"{m} meses" + (f" ({m // 12} año{'s' if m >= 24 else ''})" if m % 12 == 0 else ""))
        sl.valueChanged.connect(upd); upd(self.answers["months"])
        ends = QHBoxLayout(); ends.addWidget(QLabel("6 meses", objectName="muted")); ends.addStretch()
        ends.addWidget(QLabel("72 meses", objectName="muted"))
        tip = QLabel("⚖️  A más tiempo, la cuota mensual baja, pero al final pagas más en intereses.")
        tip.setWordWrap(True); tip.setStyleSheet("background: #fff7e6; border-radius: 10px; padding: 10px;")
        for w in (big, sl):
            cv.addWidget(w)
        cv.addLayout(ends); cv.addWidget(tip); return True

    def _q4(self, cv):
        self._title(cv, "¿Cuáles son tus ingresos mensuales?", "Incluye sueldo, ventas de tu negocio o cualquier ingreso fijo.")
        m = MoneyInput(800_000, 20_000_000, 50_000, self.answers["income"])
        m.changed.connect(lambda x: (self.answers.__setitem__("income", x), self._next.setEnabled(x > 0)))
        cv.addWidget(m); return self.answers["income"] > 0

    def _q5(self, cv):
        self._title(cv, "¿Cuánto pagas hoy en otras cuotas?", "Suma todo lo que pagas al mes por otros créditos, tarjetas o compras a cuotas. Si no tienes deudas, deja $0.")
        m = MoneyInput(0, 5_000_000, 50_000, self.answers["existing"])
        m.changed.connect(lambda x: self.answers.__setitem__("existing", x))
        quick = QHBoxLayout()
        for label, val in (("No tengo deudas", 0), ("≈ $300.000", 300_000), ("≈ $1.000.000", 1_000_000), ("≈ $2.000.000", 2_000_000)):
            b = QPushButton(label, objectName="ghost"); b.clicked.connect(lambda _=False, v=val: m.set(v)); quick.addWidget(b)
        cv.addWidget(m); cv.addLayout(quick)
        n = QLabel("Esto importa: los bancos miran cuánto de tu ingreso se va en deudas, no solo la cuota nueva.", objectName="muted")
        n.setWordWrap(True); cv.addWidget(n); return True

    def _q6(self, cv):
        self._title(cv, "¿Dónde piensas pedir el crédito?", "El tipo de entidad cambia mucho la tasa de interés.")
        g = QButtonGroup(self)
        for k, v in LENDERS.items():
            b = QPushButton(f"{v['name']}   ·   ~{self.settings['rates'][k]:.1%} E.A.\n{v['desc']}")
            b.setCheckable(True); b.setChecked(self.answers["lender"] == k); b.setMinimumHeight(58)
            b.clicked.connect(lambda _=False, k=k: (self.answers.__setitem__("lender", k), self.answers.__setitem__("ea", None),
                                                    own.setValue(0), self._next.setEnabled(True)))
            g.addButton(b); cv.addWidget(b)
        self._group = g
        row = QHBoxLayout(); row.addWidget(QLabel("¿Ya te dieron una tasa? Escríbela (E.A.):"))
        own = QDoubleSpinBox(decimals=2, maximum=200, suffix=" % E.A."); own.setSpecialValueText("Opcional")
        own.setValue((self.answers["ea"] or 0) * 100)

        def set_own(x):
            self.answers["ea"] = x / 100 if x > 0 else None
            if x > 0 and not self.answers["lender"]:
                self.answers["lender"] = "nose"
            self._next.setEnabled(self.answers["lender"] is not None)
        own.valueChanged.connect(set_own); row.addWidget(own); cv.addLayout(row)
        return self.answers["lender"] is not None

    # ---------------------------------------------------------------- result
    def show_result(self):
        a = self.answers
        self.sim = simulate(a["amount"], a["purpose"], a["months"], a["income"], a["existing"], a["lender"],
                            ea=a["ea"] if a["ea"] else self.settings["rates"][a["lender"]],
                            usury_ea=self.settings["usury"])
        self.advice_text, self.advice_src = local_advice(self.sim), "local"
        self._render_result()

    def _render_result(self):
        s, c = self.sim, self.sim.cap

        def build(lay):
            lay.addWidget(QLabel("Tu simulación", objectName="hero"))
            src = "la tasa que escribiste" if self.answers["ea"] else f"la tasa de referencia para {LENDERS[s.lender]['name']}"
            lay.addWidget(QLabel(f"Cifras estimadas con {src}.", objectName="muted"))
            if s.over_usury:
                w = QLabel(f"⚠️  Esta tasa ({s.ea:.1%} E.A.) supera la tasa de usura que configuraste ({s.usury_ea:.1%} E.A.). "
                           "Cobrar por encima de la usura es ilegal en Colombia. No firmes y pide que te expliquen la tasa.")
                w.setWordWrap(True); w.setStyleSheet(f"background: #fdecec; color: {RED}; border-radius: 12px; padding: 12px; font-weight: 600;")
                lay.addWidget(w)
            hero = QFrame(objectName="card"); hv = QVBoxLayout(hero); hv.setContentsMargins(22, 18, 22, 18)
            hv.addWidget(QLabel("CUOTA MENSUAL ESTIMADA", objectName="muted"))
            hv.addWidget(QLabel(pesos(s.monthly), objectName="value"))
            hv.addWidget(QLabel(f"durante {s.months} meses", objectName="muted"))
            lay.addWidget(hero)
            row = QHBoxLayout(); row.setSpacing(10)
            for t, v in (("TOTAL A PAGAR", pesos(s.total)), ("INTERESES", pesos(s.interest)),
                         ("TASA EFECTIVA ANUAL", f"{s.ea:.1%}"), ("TASA MENSUAL", f"{s.monthly_pct:.2%}")):
                f = QFrame(objectName="card"); fv = QVBoxLayout(f); fv.setContentsMargins(14, 12, 14, 12)
                fv.addWidget(QLabel(t, objectName="muted")); lb = QLabel(v); lb.setStyleSheet("font-size: 19px; font-weight: 700;")
                fv.addWidget(lb); row.addWidget(f)
            lay.addLayout(row)
            col = {"buena": GREEN, "ajustada": AMBER, "riesgosa": RED}[c.level]
            cap = QFrame(objectName="card"); cpv = QVBoxLayout(cap); cpv.setContentsMargins(20, 16, 20, 16)
            t = QLabel(f"Tu capacidad de pago es {c.level}", objectName="h2"); t.setStyleSheet(f"color: {col}; font-size: 17px; font-weight: 700;")
            cpv.addWidget(t)
            m = QLabel(c.message); m.setWordWrap(True); cpv.addWidget(m)
            cpv.addWidget(Bar(c.ratio_total, col))
            det = QLabel(f"Cuota nueva: {c.ratio_new:.0%} de tus ingresos · Otras cuotas: {pesos(s.existing)} · "
                         f"Para quedarte en el 30% podrías pedir hasta {pesos(c.max_loan)} con este plazo.", objectName="muted")
            det.setWordWrap(True); cpv.addWidget(det)
            lay.addWidget(cap)

            lay.addWidget(QLabel("¿Y si cambias el plazo?", objectName="h2"))
            tb = QTableWidget(len(s.alternatives), 4); tb.setHorizontalHeaderLabels(["Plazo", "Cuota", "Total", "Intereses"])
            tb.verticalHeader().setVisible(False); tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tb.setEditTriggers(QTableWidget.NoEditTriggers); tb.setSelectionMode(QTableWidget.NoSelection)
            for i, (mo, p, tot, intr) in enumerate(s.alternatives):
                mine = mo == s.months
                for j, val in enumerate((f"{mo} meses" + (" · tu elección" if mine else ""), pesos(p), pesos(tot), pesos(intr))):
                    it = QTableWidgetItem(val); it.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if j == 0 else Qt.AlignRight))
                    if mine:
                        f = it.font(); f.setBold(True); it.setFont(f); it.setForeground(QColor(BLUE))
                    tb.setItem(i, j, it)
            tb.setFixedHeight(36 + 32 * len(s.alternatives)); lay.addWidget(tb)

            adv = QFrame(objectName="card"); av = QVBoxLayout(adv); av.setContentsMargins(20, 16, 20, 16)
            head = QHBoxLayout(); head.addWidget(QLabel("Análisis personalizado", objectName="h2")); head.addStretch()
            self.ai_btn = QPushButton("Explicar con Claude" if get_key() else "Activar Claude en Ajustes", objectName="ghost")
            self.ai_btn.clicked.connect(self.run_ai if get_key() else self.open_settings); head.addWidget(self.ai_btn)
            av.addLayout(head)
            self.adv_label = QLabel(md_to_html(self.advice_text)); self.adv_label.setWordWrap(True)
            self.adv_label.setTextFormat(Qt.RichText); self.adv_label.setStyleSheet("font-size: 14px;")
            av.addWidget(self.adv_label)
            self.adv_src = QLabel("Escrito por Claude con tus números" if self.advice_src == "claude"
                                  else "Hecho por BlueCredit con tus números", objectName="muted")
            av.addWidget(self.adv_src)
            lay.addWidget(adv)

            self.sched_btn = QPushButton("Ver tabla de amortización (mes a mes)  ▾", objectName="ghost")
            self.sched = QTableWidget(len(s.rows), 5); self.sched.hide()
            self.sched.setHorizontalHeaderLabels(["Mes", "Cuota", "Intereses", "Abono a capital", "Saldo"])
            self.sched.verticalHeader().setVisible(False); self.sched.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.sched.setEditTriggers(QTableWidget.NoEditTriggers)
            for i, r in enumerate(s.rows):
                for j, val in enumerate((str(r.month), pesos(r.payment), pesos(r.interest), pesos(r.capital), pesos(r.balance))):
                    it = QTableWidgetItem(val); it.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight); self.sched.setItem(i, j, it)
            self.sched.setFixedHeight(min(420, 36 + 30 * len(s.rows)))
            self.sched_btn.clicked.connect(lambda: self.sched.setVisible(not self.sched.isVisible()))
            lay.addWidget(self.sched_btn); lay.addWidget(self.sched)

            act = QHBoxLayout()
            b1 = QPushButton("Descargar resumen (PDF)", objectName="primary"); b1.clicked.connect(self.export_pdf)
            b2 = QPushButton("Cambiar respuestas", objectName="ghost"); b2.clicked.connect(lambda: self.show_q(1))
            b3 = QPushButton("Nueva simulación", objectName="ghost"); b3.clicked.connect(self.new_sim)
            act.addWidget(b1); act.addWidget(b2); act.addWidget(b3); act.addStretch(); lay.addLayout(act)
            f = QLabel("BlueCredit · Simulación educativa, no es una oferta de crédito ni asesoría financiera profesional.",
                       objectName="muted"); f.setWordWrap(True); lay.addWidget(f)
        self._set_page(self._centered(build, 760))

    def new_sim(self):
        self.answers.update({"purpose": None, "lender": None, "ea": None}); self.show_welcome()

    def run_ai(self):
        self.ai_btn.setEnabled(False); self.ai_btn.setText("Claude está revisando tus números…")
        th = QThread(self); w = Worker(ai_advice, self.sim); w.moveToThread(th)
        th.started.connect(w.run); w.done.connect(self.on_ai); w.done.connect(th.quit)
        self._threads = [(t, x) for t, x in self._threads if not t.isFinished()]; self._threads.append((th, w)); th.start()

    def on_ai(self, res):
        self.advice_text, self.advice_src = res
        self.adv_label.setText(md_to_html(self.advice_text))
        self.adv_src.setText("Escrito por Claude con tus números" if self.advice_src == "claude" else "Hecho por BlueCredit con tus números")
        self.ai_btn.setEnabled(True); self.ai_btn.setText("Explicar con Claude")

    # ---------------------------------------------------------------- export, settings
    def report_html(self) -> str:
        s, c = self.sim, self.sim.cap
        alt = "".join(f"<tr><td>{m} meses</td><td align=right>{pesos(p)}</td><td align=right>{pesos(t)}</td>"
                      f"<td align=right>{pesos(i)}</td></tr>" for m, p, t, i in s.alternatives)
        rows = "".join(f"<tr><td>{r.month}</td><td align=right>{pesos(r.payment)}</td><td align=right>{pesos(r.interest)}</td>"
                       f"<td align=right>{pesos(r.capital)}</td><td align=right>{pesos(r.balance)}</td></tr>" for r in s.rows)
        warn = (f"<p style='color:{RED}'><b>Alerta:</b> la tasa supera la tasa de usura configurada "
                f"({s.usury_ea:.1%} E.A.).</p>") if s.over_usury else ""
        return f"""<html><body style='font-family:Helvetica; color:{TEXT}'>
        <h1 style='color:{BLUE}'>BlueCredit · Resumen de tu simulación</h1>
        <p>Monto: <b>{pesos(s.amount)}</b> · Para: {PURPOSES.get(s.purpose, '')} · Plazo: <b>{s.months} meses</b> ·
        Entidad: {LENDERS[s.lender]['name']}</p>
        <h2>Cuota mensual: {pesos(s.monthly)}</h2>
        <p>Total a pagar: <b>{pesos(s.total)}</b> · Intereses: <b>{pesos(s.interest)}</b> ·
        Tasa: <b>{s.ea:.2%} E.A.</b> ({s.monthly_pct:.3%} mensual)</p>{warn}
        <p><b>Capacidad de pago: {c.level}.</b> {c.message}</p>
        <h3>Comparación de plazos</h3><table border=1 cellspacing=0 cellpadding=4 width=100%>
        <tr><th>Plazo</th><th>Cuota</th><th>Total</th><th>Intereses</th></tr>{alt}</table>
        <h3>Análisis</h3>{md_to_html(self.advice_text)}
        <h3>Tabla de amortización</h3><table border=1 cellspacing=0 cellpadding=3 width=100%>
        <tr><th>Mes</th><th>Cuota</th><th>Intereses</th><th>Capital</th><th>Saldo</th></tr>{rows}</table>
        <p style='color:{MUTED}'>Simulación educativa de BlueCredit (Blue Peak AI &amp; Finance Solutions). No es una oferta de crédito.</p>
        </body></html>"""

    def export_pdf(self, path: str | None = None):
        if not self.sim:
            return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Guardar resumen", str(Path.home() / "BlueCredit simulación.pdf"), "PDF (*.pdf)")
        if not path:
            return
        printer = QPrinter(QPrinter.HighResolution); printer.setOutputFormat(QPrinter.PdfFormat); printer.setOutputFileName(path)
        doc = QTextDocument(); doc.setHtml(self.report_html()); doc.print_(printer)

    def open_settings(self):
        d = SettingsDialog(self, self.settings)
        if d.exec():
            self.settings = d.values(self.settings); save_settings(self.settings)
            if self.sim:
                self.show_result()

    def about(self):
        QMessageBox.about(self, "Acerca de BlueCredit",
                          f"<b>BlueCredit {__version__}</b><br>Simulador de crédito de Blue Peak AI &amp; Finance Solutions."
                          "<br><br>Tasas en efectiva anual, cuota por sistema francés, capacidad de pago con todas tus deudas "
                          "y alerta de usura.<br><br>Simulación educativa, no es una oferta de crédito.")


def main():
    app = QApplication(sys.argv); app.setApplicationName("BlueCredit"); app.setStyleSheet(QSS)
    if (ASSETS / "icon.png").exists():
        app.setWindowIcon(QIcon(str(ASSETS / "icon.png")))
    w = MainWindow(); w.show()
    snap = os.environ.get("BLUECREDIT_SNAPSHOT")      # used to make the README screenshots
    if snap:
        def shoot():
            w.answers.update({"amount": 5_000_000, "purpose": "negocio", "months": 24, "income": 2_500_000,
                              "existing": 300_000, "lender": "cooperativa", "ea": None})
            w.show_q(3); QApplication.processEvents(); w.grab().save(f"{snap}-question.png")
            w.show_result(); QApplication.processEvents()
            w.stack.currentWidget().widget().grab().save(f"{snap}-result.png")
            w.export_pdf(f"{snap}-summary.pdf"); app.quit()
        QTimer.singleShot(800, shoot)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
