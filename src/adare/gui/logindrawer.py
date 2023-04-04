from adare.gui.colors import TAILWIND_GRADIENTS
from adare.gui.extensions.icon import IconExtension

from nicegui import ui


class LoginDrawer:
    ui_self = None

    def create(self):
        with ui.right_drawer(value=False).classes(f'bg-{TAILWIND_GRADIENTS.emerald_blue} self-end justify-center') as right_drawer:
            self.ui_self = right_drawer
            with ui.column().classes('w-full items-center'):
                with ui.row().classes('w-full items-center justify-center'):
                    ui.icon('account_circle').classes('text-cyan-900 text-8xl')
                with ui.row().classes('w-full'):
                    ui.input(label='username').classes('w-full bg-white border-gray-400 rounded-lg px-6 py-2')
                with ui.row().classes('w-full'):
                    with ui.input(label='password').props('type=password').classes \
                            ('w-full bg-white border-gray-400 rounded-lg px-6 py-2') as inp:
                        with inp.add_slot('append'):
                            icon = ui.icon('cursor-pointer').props('name=visibility_off').classes('text-gray-400')
                            IconExt = IconExtension(icon)
                            icon.on('click', lambda: IconExt.set_visibility(inp))

                with ui.row().classes('w-full'):
                    btn = ui.button('Login')
                    del btn._props['color']
                    btn.classes('w-1/2 ml-auto text-blue-800 bg-slate-300')
