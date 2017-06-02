#!/usr/bin/env python
import urwid
import urwid_utils
import sys, re, os
import pandas as pd
from dataframe_browser import DataframeTableBrowser
from keybindings import keybs

from gui_debug import *

PAGE_SIZE = 20

# this stuff captures Ctrl-C
# ui = urwid.raw_display.RealTerminal()
# ui.tty_signal_keys('undefined', 'undefined', 'undefined', 'undefined',
#                    'undefined')

def _pack(columns): # this just exists to cut down code bloat
    return columns.options(width_type='pack')
def _given(columns, width):
    return columns.options('given', width)

def display_browser_in_urwid_columns(urwid_cols, browser, focus_col, is_focus_col,
                                     set_focus_column_by_name):
    del urwid_cols.contents[:]
    # TODO don't recreate these column piles - instead keep track of them
    # and re-order/refresh them as necessary, only creating new ones when brand new columns are shown
    for idx, col_name in enumerate(browser.browse_columns):
        pile = BrowserNamedColumnPile(browser.view, col_name, is_focus_col,
                                      set_focus_column_by_name)
        column_width = browser.view.width(col_name)
        urwid_cols.contents.append((pile, _given(urwid_cols, column_width)))
    try:
        urwid_cols.focus_position = focus_col
    except Exception as e:
        print('exception in display_browser_in_urwid_columns', e)

def generate_strings_segments_for_column(view, col_name, is_focus_col):
    column_strings = view.lines(col_name)
    selected_row = view.selected_relative
    pile_of_strs = list()
    pile_of_strs.append(view.header(col_name) +
                        '\n...' if view.top_row > 1 and is_focus_col else '\n')
    if selected_row > 0:
        pile_of_strs.append('\n'.join(column_strings[0:selected_row]))
    pile_of_strs.append(column_strings[selected_row])
    pile_of_strs.append('\n'.join(column_strings[selected_row + 1: len(column_strings)]))
    return pile_of_strs

def set_attrib_on_col_pile(pile, is_focus_col, focus_pile):
    for i in range(len(pile.contents)):
        if focus_pile == i:
            pile.contents[i][0].set_attr_map({None: 'active_element' if is_focus_col else 'active_row'})
        else:
            pile.contents[i][0].set_attr_map({None: 'active_col' if is_focus_col else 'def'})

class BrowserNamedColumnPile(urwid.Pile):
    def __init__(self, browser_view, column_name, is_focus_col_cb, set_focus_cb):
        super().__init__([])
        self.browser_view = browser_view
        self.column_name = column_name
        self.is_focus_col = is_focus_col_cb
        self.set_focus_to_column = set_focus_cb
        self._focus_pile = 0
        self._create_pile()
        self.rebuild_from_view()
    def _create_pile(self, num_texts=5):
        for i in range(num_texts):
            self.contents.append((urwid.AttrMap(
                urwid.Text('', align=self.browser_view.justify(self.column_name)), 'def'),
                                  ('pack', None)))
    @property
    def is_focused(self):
        return self.is_focus_col(self.column_name)
    def selectable(self):
        return True
    def mouse_event(self, size, event, button, col, row, focus):
        # TODO implement scrolling. shouldn't be terribly hard. events 4.0 and 5.0.
        print('srp got mouse event', size, event, button, col, row, focus, self.column_name)
        if event == 'mouse press':
            self.set_focus_to_column(self.column_name, max(row-2, 0))
        return True
    def keypress(self, size, key):
        return False # we don't handle these
    def rebuild_from_view(self):
        pile_strings = generate_strings_segments_for_column(
            self.browser_view, self.column_name, self.is_focused)
        for idx, pile_str in enumerate(pile_strings):
            self.contents[idx][0].original_widget.set_text(pile_str)
        self._focus_pile = len(pile_strings) - 2
        self.reset_attribs()
    def _set_header_break(self):
        header = self.browser_view.header(self.column_name)
        # header += '\n...' if view.top_row > 1 and is_focus_col else '\n'
        header += '\n...' if self.is_focused and self.browser_view.top_row > 1 else '\n'
        self.contents[0][0].original_widget.set_text(header)
    def reset_attribs(self):
        self._set_header_break()
        set_attrib_on_col_pile(self, self.is_focused, self._focus_pile)


class Modeline(urwid.WidgetWrap):
    # TODO use modeline to communicate table name, total table length, number of columns,
    # table percentage at current selection, current row and column number
    def __init__(self):
        self.text = urwid.Text('Welcome to the Dataframe browser!')
        urwid.WidgetWrap.__init__(self, self.text)
    def set_text(self, text):
        self.text.set_text(text)
    def show_basic_commands(self):
        # help text
        self.set_text('(hjkl) browse; (H)ide col; (u)ndo; (+-) size col; (,.) move col; (ctrl-s)ea(r)ch col; (s)o(r)t')
    def show_command_options(self):
        self.set_text('type column name to add, then press enter. Press Esc to return to browsing.')


class Minibuffer(urwid.WidgetWrap):
    # TODO modify the minibuffer so it knows very little about the
    # browser_frame, but instead sends 'results' to the browser
    # via strings that the browser can that use to determine which functions,
    # if any, to call.
    # The advantage is reduced coupling that will further enhance the ability of the
    # UrwidBrowser to support back end browser implementations that don't necessarily
    # support 100% of the same functionality (i.e. maybe not supporting JOINs).
    def __init__(self, browser_frame):
        self.browser_frame = browser_frame
        self.edit_text = urwid_utils.AdvancedEdit(caption='browsing... ', multiline=False)
        urwid.WidgetWrap.__init__(self, self.edit_text)
        self.active_command = 'browsing'
        self.active_args = dict()
    def focus_granted(self, command, **kwargs):
        self._set_command(command, **kwargs)
    def focus_removed(self):
        self._set_command('browsing')
        self.edit_text.set_caption('browsing... ')
        self.edit_text.setCompletionMethod()
    def give_away_focus(self):
        # this should call back to focus_removed
        self.edit_text.set_edit_text('')
        self.active_args = dict()
        self.browser_frame.focus_browser()
    def _set_command(self, command, **kwargs):
        self.active_command = command
        self.active_args = kwargs
        self.edit_text.set_caption(command + ': ')
        if self.active_command == 'query':
            self.edit_text.set_edit_text(self.active_args['column_name'])
            self.edit_text.set_edit_pos(len(self.edit_text.get_edit_text()) + 1)
        if 'completer' in self.active_args:
            self.edit_text.setCompletionMethod(self.active_args['completer'])
        if 'default_text' in self.active_args:
            self.edit_text.set_edit_text(self.active_args['default_text'])
            self.edit_text.set_edit_pos(len(self.edit_text.get_edit_text()))
        if self.active_command == None:
            # then we are typing in a custom command, so set up appropriately...
            self.edit_text.set_caption('command? ')
            self.edit_text.set_edit_text('')
            self.edit_text.setCompletionMethod(keybindings._commands.keys())

    def _search(self, search_str, down, skip_current):
        if 'search' in self.active_command:
            if down:
                self._set_command('search')
            else:
                self._set_command('search backward')
            self.browser_frame.table_view.search_current_col(search_str, down, skip_current)

    def keypress(self, size, key):
        if key == 'enter':
            cmd_str = self.edit_text.get_edit_text().strip()
            print('handling input string', cmd_str)
            if self.active_command == 'query':
                self.browser_frame.table_view.browser.query(cmd_str)
                self.give_away_focus()
            elif self.active_command == 'add':
                if self.browser_frame.table_view.insert_column(cmd_str):
                    self.give_away_focus()
                else:
                    self.browser_frame.modeline.set_text(str(cmd_str) + ' column not found in table browser')
            elif self.active_command == 'name current table browser':
                self.browser_frame.table_view.name_current_browser(cmd_str)
                self.give_away_focus()
            elif self.active_command == 'switch to table browser':
                self.browser_frame.table_view.switch_to_browser(cmd_str)
                self.give_away_focus()
            elif self.active_command == None:
                # we've typed in a custom command!
                self.edit_text.set_caption(cmd_str)
            else:
                pass # do nothing - we don't know how to accept this input.
        elif key == 'esc' or key == 'ctrl g':
            self.give_away_focus()
        elif key == 'ctrl c':
            # raise urwid.ExitMainLoop()
            self.give_away_focus()
        elif key == 'ctrl s':
            self._search(self.edit_text.get_edit_text(), True, True)
        elif key == 'ctrl r':
            self._search(self.edit_text.get_edit_text(), False, True)
        else: # active search - TODO maybe replace with 'active results' being fed directly to the command callback
            self.edit_text.keypress(size, key)
            if key != 'backspace':
                if self.active_command == 'search':
                    print('asking for forward search')
                    self._search(self.edit_text.get_edit_text(), True, False)
                elif self.active_command == 'search backward':
                    print('asking for backward search')
                    self._search(self.edit_text.get_edit_text(), False, False)


class UrwidTableView(urwid.WidgetWrap):
    def __init__(self, urwid_frame):
        self.urwid_frame = urwid_frame
        self.urwid_cols = urwid.Columns([], dividechars=2)
        urwid.WidgetWrap.__init__(self, self.urwid_cols)

    @property
    def browser(self):
        return self.multibrowser.current_browser
    @property
    def active_browser_name(self):
        return self.multibrowser.current_browser_name
    @property
    def focus_column(self):
        return self._col_by_index(self.focus_pos)
    @property
    def focus_pos(self):
        return self.browser.focused_column
    def _col_by_index(self, idx):
        return self.browser.browse_columns[idx]
    def _col_idx_by_name(self, column_name):
        for idx, colname in enumerate(self.browser.browse_columns):
            if colname == column_name:
                return idx
    def is_focus_column(self, column_name):
        return column_name == self.focus_column

    # def translate_urwid_colrow_to_browser_colrow(self, ucol, urow):
    #     col = 0
    #     next_col_start = self.browser.view.width(self.browser.browse_columns[col])
    #     while ucol > next_col_start:
    #         col += 1
    #         next_col_start += self.browser.view.width(self.browser.browse_columns[col]) + 1
    #     self.set_col_focus(col)
    #     print(col, self.browser.browse_columns[col])

    def set_multibrowser(self, multibrowser):
        self.multibrowser = multibrowser
        self.update_view()

    def switch_to_browser(self, name):
        """Open an existing dataframe, or accept a new one."""
        print('switching to', name)
        self.multibrowser.set_current_browser(name)
        self.update_view()

    def name_current_browser(self, new_name):
        self.multibrowser.rename_current_browser(new_name)

    def update_view(self, browser=None):
        print('updating view')
        if len(self.browser.browse_columns) > 0:
            display_browser_in_urwid_columns(self.urwid_cols, self.browser,
                                             self.focus_pos, self.is_focus_column,
                                             self.set_focus_to_column_by_name)
            self.update_text()

    def set_focus_to_column_by_name(self, column_name, row):
        print('trying to set focus to column', column_name)
        self.set_col_focus(self._col_idx_by_name(column_name))
        if row != self.browser.view.selected_relative:
            self.scroll(row - self.browser.view.selected_relative)

    def update_text(self):
        self.urwid_frame.modeline.set_text(str(self.browser.view.selected_row_content(
            self.browser.browse_columns[self.urwid_cols.focus_position])))

    def scroll(self, num_rows):
        self.browser.view.scroll_rows(num_rows)
        self.update_view()

    # def mouse_event(self, size, event, button, col, row, focus):
    #     print(size, focus)
    #     print(self.urwid_cols.column_widths(size))
    #     print(self.urwid_cols.get_cursor_coords(size))

    def set_col_focus(self, col_num):
        # the only function allowed to deal directly with urwid_cols.focus_position
        col_num = max(0, min(col_num, len(self.urwid_cols.contents) - 1))
        try:
            current_focus_pos = self.focus_pos #self.urwid_cols.focus_position
            if current_focus_pos != col_num:
                self.urwid_cols.focus_position = col_num
                self.browser.focused_column = col_num
                self.urwid_cols.contents[current_focus_pos][0].reset_attribs()
                self.urwid_cols.contents[col_num][0].reset_attribs()
                self.update_text()
            return True
        except Exception as e:
            print('exception in set focus', e)
            return False

    def search_current_col(self, search_string, down=True, skip_current=False):
        if self.browser.search_column(self.focus_column, search_string, down, skip_current):
            self.update_view()
        else:
            # TODO could print help text saying the search failed.
            # TODO also, could potentially try wrapping the search just like emacs...
            pass

    def shift_col(self, shift_num):
        if self.browser.shift_column(self.urwid_cols.focus_position, shift_num):
            self.urwid_cols.focus_position += shift_num
            self.browser.focused_column += shift_num
            self.update_view() # TODO this incurs a double update penalty but is necessary because the focus_position can't change until we know that the shift column was actually doable/successful

    def jump_to_col(self, num):
        num = num if num >= 0 else 9 # weird special case for when the input was a '0' key
        self.set_col_focus(num)

    def change_column_width(self, by_n):
        self.browser.view.change_column_width(self.focus_column, by_n)
        self.urwid_cols.contents[self.focus_pos] = (self.urwid_cols.contents[self.focus_pos][0],
                                                    _given(self.urwid_cols, self.browser.view.width(self.focus_column)))

    def sort_current_col(self, ascending=True):
        self.browser.sort_on_columns([self.focus_column], ascending=ascending)

    def insert_column(self, col_name, idx=None):
        try:
            if not idx or idx < 0 or idx > self.urwid_cols.focus_position:
                idx = self.focus_pos
        except Exception as e: # if for some reason cols.focus_position doesn't exist at all...
            print('exception in insert column', e)
            idx = 0
        return self.browser.insert_column(col_name, idx)

    def hide_current_col(self):
        return self.browser.hide_col_by_index(self.focus_pos)

    def _get_completer_with_hint(self, lst):
        return urwid_utils.ListCompleter(lst, self.urwid_frame.hint).complete

    # BROWSE COMMANDS
    def keypress(self, size, key):
        # TODO move key bindings into dict of arrays
        if key in keybs('merge'):
            pass
        elif key in keybs('hide column'):
            self.hide_current_col()
        elif key in keybs('search down'):
            self.urwid_frame.focus_minibuffer('search')
        elif key in keybs('search up'):
            self.urwid_frame.focus_minibuffer('search backward')
        elif key in keybs('sort ascending'):
            self.sort_current_col(ascending=True)
        elif key in keybs('sort descending'):
            self.sort_current_col(ascending=False)
        elif key == 'f':
            pass # filter?
        elif key == 'i':
            self.urwid_frame.focus_minibuffer('add', completer=self._get_completer_with_hint(
                list(self.browser.all_columns)))
        elif key in keybs('browse right'):
            self.set_col_focus(self.focus_pos + 1)
        elif key in keybs('browse left'):
            self.set_col_focus(self.focus_pos - 1)
        elif key in keybs('browse down'):
            self.scroll(+1)
        elif key in keybs('browse up'):
            self.scroll(-1)
        elif key in keybs('undo'):
            self.browser.undo()
        elif key in keybs('quit'):
            raise urwid.ExitMainLoop()
        elif key in keybs('query'):
            self.urwid_frame.focus_minibuffer('query', column_name=self.focus_column)
        elif key in keybs('page up'):
            self.scroll(-PAGE_SIZE)
        elif key in keybs('page down'):
            self.scroll(PAGE_SIZE)
        elif key in keybs('help'):
            self.urwid_frame.modeline.show_basic_commands()
        elif key in keybs('shift column left'):
            self.shift_col(-1)
        elif key in keybs('shift column right'):
            self.shift_col(1)
        elif key in keybs('increase column width'):
            self.change_column_width(1)
        elif key in keybs('decrease column width'):
            self.change_column_width(-1)
        elif key in keybs('jump to last row'):
            self.browser.view.jump(fraction=1.0)
            self.update_view()
        elif key in keybs('jump to first row'):
            self.browser.view.jump(fraction=0.0)
            self.update_view()
        elif key in keybs('jump to numeric column'):
            self.jump_to_col(int(key) - 1) # 1-based indexing when using number keys
        elif key in keybs('jump to last column'):
            self.jump_to_col(len(self.browser.browse_columns) - 1)
        elif key in keybs('jump to first column'):
            self.jump_to_col(0)
        elif key in keybs('name current table browser'):
            self.urwid_frame.focus_minibuffer('name current table browser',
                                              default_text=self.multibrowser.current_browser_name)
        elif key in keybs('switch to table browser'):
            self.urwid_frame.focus_minibuffer('switch to table browser',
                                              completer=self._get_completer_with_hint(
                                                  self.multibrowser.all_browser_names))
        else:
            self.urwid_frame.hint('got unknown keypress: ' + key)
            return None

def trace_keyp(size, key):
    if key == 'p':
        raise urwid.ExitMainLoop()
    else:
        return None

palette = [
    ('active_col', 'light blue', 'black'),
    ('def', 'white', 'black'),
    ('modeline', 'black', 'light gray'),
    ('moving', 'light red', 'black'),
    ('active_row', 'dark red', 'black'),
    ('active_element', 'yellow', 'black'),
    ]


# there really only ever needs to be one of these instantiated at a given time,
# because it supports having arbitrary browser implementations
# assigned at any time
class TableBrowserUrwidLoopFrame:
    def __init__(self):
        self.modeline = Modeline()
        self.modeline.show_basic_commands()
        self.minibuffer = Minibuffer(self)
        self.table_view = UrwidTableView(self)
        self.inner_frame = urwid.Frame(urwid.Filler(self.table_view, valign='top'),
                                       footer=urwid.AttrMap(self.modeline, 'modeline'))
        self.frame = urwid.Frame(self.inner_frame, footer=self.minibuffer)
    def start(self, multibrowser):
        loop = urwid.MainLoop(self.frame, palette, # input_filter=self.input,
                              unhandled_input=self.unhandled_input)
        self.table_view.set_multibrowser(multibrowser)
        loop.run()
    def focus_minibuffer(self, command, **kwargs):
        self.frame.focus_position = 'footer'
        self.minibuffer.focus_granted(command, **kwargs)
        self.modeline.show_command_options()
    def focus_browser(self):
        self.frame.focus_position = 'body'
        self.minibuffer.focus_removed()
        self.modeline.show_basic_commands()
    def keypress(self, size, key):
        raise urwid.ExitMainLoop('keypress in DFbrowser!')
    # def input(self, inpt, raw):
    #     print('ipt')
    #     return inpt
    def unhandled_input(self, key):
        if key == 'q' or key == 'Q':
            raise urwid.ExitMainLoop()
        elif key == 'ctrl c':
            self.modeline.set_text('got Ctrl-C')
        else:
            print('unhandled input ' + str(key))
    def hint(self, text):
        self.modeline.set_text(text)

# TODO this is a convenience that should probably move elsewhere eventually
# def read_all_dfs_from_dir(directory):
#     dataframes_and_names = list()
#     for fn in os.listdir(directory):
#         df = pd.DataFrame.from_csv(directory + os.sep + fn)
#         name = fn[:-4]
#         dataframes_and_names.append((df, name))
#     return dataframes_and_names

# def start_browser(dfs_and_names, df_name='dubois_mathlete_identities'):
#     # st()
#     global urwid_frame
#     urwid_frame = TableBrowserUrwidLoopFrame()
#     for df, name in dfs_and_names:
#         urwid_frame.browse(df, name)
#     urwid_frame.browse(None, df_name)
#     urwid_frame.start()
#     return urwid_frame

# if __name__ == '__main__':
#     # pd.set_option('display.max_rows', 9999)
#     # pd.set_option('display.width', None)
#     try:
#         local_data = sys.argv[1]
#         start_browser(read_all_dfs_from_dir(local_data))
#     except (KeyboardInterrupt, EOFError) as e:
#         print('\nLeaving the DuBois Project Data Explorer.')