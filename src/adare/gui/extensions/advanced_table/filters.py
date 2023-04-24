from nicegui import ui


class MultipleFilter:
    """ Class for multiple filters. """
    table = None
    filters: dict = {}

    def set_table(self, table):
        self.table = table

    def set_filters(self, filters):
        for index, filter_obj in filters.items():
            self.add_filter(filter_obj, index)

    def add_filter(self, filter_obj, index: int):
        self.filters[index] = filter_obj

    def remove_filter(self, index: int):
        del self.filters[index]


    def filter_data(self):
        bool_lists = []
        for filter_obj in self.filters.values():
            if not filter_obj:
                continue
            if filter_obj.comparison_value:
                bool_list_show = filter_obj.filter_data(self.table)
            else:
                bool_list_show = [True] * len(self.table.data)
            bool_lists.append(bool_list_show)
        bool_list_show = [all(x) for x in zip(*bool_lists)]
        if not bool_list_show:
            bool_list_show = [True] * len(self.table.data)
        self.table.set_shown_rows(bool_list_show)
        self.table.update()


class Filter:
    """ Base class for all filters. """
    name: str = None
    data: list = None

    column_name: str = None
    comparison_value = None

    def set_column_name(self, column_name):
        self.column_name = column_name

    def set_comparison_value(self, comparison_value):
        self.comparison_value = comparison_value


    def create_comparison_value_input(self, table, index, filter_container: MultipleFilter,  container=None, default_value=None):
        pass

    @classmethod
    def filter_row(cls, value, comparison_value) -> bool:
        pass

    def filter_data(self, table):
        bool_list_show = []
        if self.comparison_value:
            for row in table.data:
                bool_list_show.append(self.filter_row(row[self.column_name], self.comparison_value))
        return bool_list_show




class FilterEqual(Filter):
    """ Filter for equal comparison. """
    name: str = '=='

    def create_comparison_value_input(self, table, index, filter_container: MultipleFilter, container=None, default_value=None):
        with container:
            self.set_column_name(self.column_name)
            filter_container.add_filter(self, index)
            inp = ui.input(on_change=lambda e: (
                self.set_comparison_value(e.value),
                filter_container.filter_data(),

            ), value=default_value)
        return inp

    @classmethod
    def filter_row(cls, value, comparison_value) -> bool:
        return value == comparison_value


class FilterNotEqual(Filter):
    """ Filter for not equal comparison. """
    name: str = '!='

    def create_comparison_value_input(self, table, index, filter_container: MultipleFilter, container=None, default_value=None):
        with container:
            self.set_column_name(self.column_name)
            filter_container.add_filter(self, index)
            inp = ui.input(on_change=lambda e: (
                self.set_comparison_value(e.value),
                filter_container.filter_data(),

            ), value=default_value)
        return inp

    @classmethod
    def filter_row(cls, value, comparison_value) -> bool:
        return value != comparison_value


class FilterContains(Filter):
    """ Filter for contains comparison. """
    name: str = 'contains'

    def create_comparison_value_input(self, table, index, filter_container: MultipleFilter, container=None, default_value=None):
        with container:
            self.set_column_name(self.column_name)
            filter_container.add_filter(self, index)
            inp = ui.input(on_change=lambda e: (
                self.set_comparison_value(e.value),
                filter_container.filter_data()
            ), value=default_value)
        return inp

    @classmethod
    def filter_row(cls, value, comparison_value) -> bool:
        return comparison_value in value
