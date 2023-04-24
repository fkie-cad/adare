""" color settings for the gui """

from nicegui import ui


class QuasarColors:
    """ Quasar Colors namespace for the project to use with tailwind (https://quasar.dev/style/color-palette) """
    primary = '#009374'
    secondary = '#26A69A'
    accent = '#9C27B0'
    # dark = '#1d1d1d
    # dark-page = '#121212'
    positive = '#21BA45'
    negative = '#C10015'
    info = '#31CCEC'
    warning = '#F2C037'

QUASAR_COLORS = QuasarColors()


def set_colors():
    """ Set the colors for the gui """
    ui.colors(
        primary=QUASAR_COLORS.primary,
        secondary=QUASAR_COLORS.secondary,
        accent=QUASAR_COLORS.accent,
        positive=QUASAR_COLORS.positive,
        negative=QUASAR_COLORS.negative,
        info=QUASAR_COLORS.info,
        warning=QUASAR_COLORS.warning,
    )


class TailwindGradients:
    """ Tailwind gradients namespace for the project to use with tailwind (https://tailwindcss.com/docs/gradient-color-stops) """
    emerald_blue = 'gradient-to-br from-emerald-400 to-blue-400'
    shiny_button = 'gradient-to-l from-yellow-600 to-red-600'

TAILWIND_GRADIENTS = TailwindGradients()

