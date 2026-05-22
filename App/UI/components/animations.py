from PySide6 import QtCore


class WindowAnimator:
    @staticmethod
    def fade_in(window, duration=200):
        window.setWindowOpacity(0)
        anim = QtCore.QPropertyAnimation(window, b"windowOpacity")
        anim.setDuration(duration)
        anim.setStartValue(0)
        anim.setEndValue(1)
        anim.start()
        window._anim = anim  # prevent garbage collection

    @staticmethod
    def fade_out(window, callback=None, duration=200):
        anim = QtCore.QPropertyAnimation(window, b"windowOpacity")
        anim.setDuration(duration)
        anim.setStartValue(1)
        anim.setEndValue(0)

        if callback:
            anim.finished.connect(callback)

        anim.start()
        window._anim = anim

    @staticmethod
    def slide(window, start_pos, end_pos, duration=180):
        anim = QtCore.QPropertyAnimation(window, b"pos")
        anim.setDuration(duration)
        anim.setStartValue(start_pos)
        anim.setEndValue(end_pos)
        anim.start()
        window._slide_anim = anim

    @staticmethod
    def minimize(window, duration=180):
        if getattr(window, "_animating", False):
            return  # prevent double trigger

        window._animating = True

        base = window.pos()  # 🔥 lock real position (NOT _base_pos)

        start_pos = base
        end_pos = base + QtCore.QPoint(0, 40)

        pos_anim = QtCore.QPropertyAnimation(window, b"pos")
        pos_anim.setDuration(duration)
        pos_anim.setStartValue(start_pos)
        pos_anim.setEndValue(end_pos)

        fade_anim = QtCore.QPropertyAnimation(window, b"windowOpacity")
        fade_anim.setDuration(duration)
        fade_anim.setStartValue(1)
        fade_anim.setEndValue(0)

        pos_anim.setEasingCurve(QtCore.QEasingCurve.InCubic)
        fade_anim.setEasingCurve(QtCore.QEasingCurve.InQuad)

        group = QtCore.QParallelAnimationGroup()
        group.addAnimation(pos_anim)
        group.addAnimation(fade_anim)

        def finish():
            window._animating = False
            window.setWindowOpacity(1)
            window.move(base)
            window.setWindowState(QtCore.Qt.WindowMinimized)

        group.finished.connect(finish)
        group.start()

        window._min_anim = group

    @staticmethod
    def restore(window, duration=180):
        base = window._base_pos

        # 🔥 IMPORTANT: show FIRST and force visible
        window.showNormal()
        window.raise_()
        window.activateWindow()

        start_pos = base + QtCore.QPoint(0, 40)
        end_pos = base

        window.move(start_pos)
        window.setWindowOpacity(0)  # start from invisible

        pos_anim = QtCore.QPropertyAnimation(window, b"pos")
        pos_anim.setDuration(duration)
        pos_anim.setStartValue(start_pos)
        pos_anim.setEndValue(end_pos)

        fade_anim = QtCore.QPropertyAnimation(window, b"windowOpacity")
        fade_anim.setDuration(duration)
        fade_anim.setStartValue(0)
        fade_anim.setEndValue(1)

        group = QtCore.QParallelAnimationGroup()
        group.addAnimation(pos_anim)
        group.addAnimation(fade_anim)

        group.start()
        window._restore_anim = group
