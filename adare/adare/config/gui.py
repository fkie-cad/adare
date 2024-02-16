
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'
TIMESTAMP_FORMAT_SECONDS = '%Y-%m-%d %H:%M:%S'
TIMESTAMP_FORMAT_DATE = '%Y-%m-%d'


STATUS_COLOR_MAPPING = {
    'success': 'green',
    'failed': 'red',
    'warning': 'yellow-10',
    'not reached': 'blue-grey-7',
    'in request': 'pink-10',
    'published': 'green',
    'not published': 'grey-7',
    'unknown': 'grey-7',
}

# full icon with round, triangle or square border
STATUS_ICON_MAPPING = {
    'success': 'check_circle',
    'failed': 'cancel',
    'warning': 'exclamation',
    'not reached': 'help',
    'in request': 'hourglass_empty',
    'published': 'check_box',
    'not published': 'unpublished',
    'unknown': 'help',
}

# only the symbol of the icon (!,?, ...,)
STATUS_SYMBOL_MAPPING = {
    'success': 'check',
    'failed': 'close',
    'warning': 'warning',
    'not reached': 'question_mark',
    'in request': 'hourglass_empty',
    'published': 'check_box',
    'not published': 'unpublished',
    'unknown': 'question_mark',
}

def __generate_status_table_slot():
    slot_string = """<q-td :props="props" auto-width>"""
    for index, status in enumerate(STATUS_ICON_MAPPING.keys()):
        if index == 0:
            slot_string += f"""
                <q-icon name="{STATUS_ICON_MAPPING[status]}" color="{STATUS_COLOR_MAPPING[status]}" v-if="props.value == '{status}'" size="2rem">
            """
        else:
            slot_string += f"""
                <q-icon name="{STATUS_ICON_MAPPING[status]}" color="{STATUS_COLOR_MAPPING[status]}" v-else-if="props.value == '{status}'" size="2rem">
            """
        slot_string += """<q-tooltip> {{ props.value }} </q-tooltip></q-icon>"""
    slot_string += """<p v-else>{{ props.value }} </p></q-td>"""
    return slot_string

SLOT_STATUS_TABLE = __generate_status_table_slot()
