
class IconExtension:
    visible: bool = False
    icon = None

    def __init__(self, icon):
        self.icon = icon

    def set_visibility(self, input_field):
        self.visible = not self.visible
        if self.visible:
            self.icon.props('name=visibility')
            input_field.props('type=text')
        else:
            self.icon.props('name=visibility_off')
            input_field.props('type=password')