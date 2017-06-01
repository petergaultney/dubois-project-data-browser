#!/usr/bin/env python
import urwid
import urwid_utils
import sys, re, os
import pandas as pd
from dataframe_browser import DataframeBrowser
from keybindings import keybs

from _debug import *

PAGE_SIZE = 20

# this stuff captures Ctrl-C
# ui = urwid.raw_display.RealTerminal()
# ui.tty_signal_keys('undefined', 'undefined', 'undefined', 'undefined',
#                    'undefined')

def _pack(columns): # this just exists to cut down code bloat
    return columns.options(width_type='pack')
def _given(columns, width):
    return columns.options('given', width)

def display_browser_in_urwid_columns(urwid_cols, browser, focus_col):
    # end('kp to kp') # DEBUG
    # st() # DEBUG
    # st() # DEBUG
    del urwid_cols.contents[:]

    for idx, col_name in enumerate(browser.browse_columns):
        pile = create_column_pile(urwid_cols, browser.view, col_name, idx == focus_col)
        column_width = browser.view.width(col_name)
        urwid_cols.contents.append((pile, _given(urwid_cols, column_width)))
    try:
        urwid_cols.focus_position = focus_col
    except Exception as e:
        print('exception in display_browser_in_urwid_columns', e)
    # end('col')

def create_column_pile(urwid_cols, view, col_name, is_focus_col):
    col_disp_attr = 'def' if not is_focus_col else 'active_col'
    selected_row_attr = 'active_element' if is_focus_col else 'active_row'
    selected_row = view.selected_relative
    column_header = view.header(col_name)
    column_strings = view.lines(col_name)
    align = view.justify(col_name)
    part_one = column_header
    part_one += '\n...\n' if view.top_row > 1 and is_focus_col else '\n\n'
    part_one += '\n'.join(column_strings[0:selected_row])
    part_two =  '\n'.join(column_strings[selected_row + 1: len(column_strings)])
    return create_column_from_text_and_attrib(part_one, column_strings[selected_row], part_two,
                                              col_disp_attr, selected_row_attr, align)


def create_column_from_text_and_attrib(part_one, selected_row_text, part_two, col_attrib,
                                       selected_row_attrib, align):
    pile = urwid.Pile([])
    pile.contents.append((urwid.AttrMap(SelectableText(part_one, align=align), col_attrib), ('pack', None)))
    pile.contents.append((urwid.AttrMap(SelectableText(selected_row_text, align=align), selected_row_attrib), ('pack', None)))
    pile.contents.append((urwid.AttrMap(SelectableText(part_two, align=align), col_attrib), ('pack', None)))
    pile.focus_position = 1
    return pile


def set_attrib_on_col_pile(pile, is_focus_col):
    pile.contents[0][0].set_attr_map({None: 'active_col' if is_focus_col else 'def'})
    pile.contents[1][0].set_attr_map({None: 'active_element' if is_focus_col else 'active_row'})
    pile.contents[2][0].set_attr_map({None: 'active_col' if is_focus_col else 'def'})


class Modeline(urwid.WidgetWrap):
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
    def keypress(self, size, key):
        raise urwid.ExitMainLoop('somehow put focus on help text!')


class Minibuffer(urwid.WidgetWrap):
    def __init__(self, urwid_browser):
        self.urwid_browser = urwid_browser
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
        self.urwid_browser.focus_browser()
    def merge(self, completion_cb=None):
        # TODO this looks bad
        self.edit_text.setCompletionMethod(completion_cb)
        self.edit_text.set_caption('merge with: ')
        self.urwid_browser.frame.focus_position = 'footer'
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

    def _search(self, search_str, down, skip_current):
        if 'search' in self.active_command:
            if down:
                self._set_command('search')
            else:
                self._set_command('search backward')
            self.urwid_browser.colview.search_current_col(search_str, down, skip_current)
    def keypress(self, size, key):
        if key == 'enter':
            cmd_str = self.edit_text.get_edit_text().strip()
            print('handling input string', cmd_str)
            if self.active_command == 'query':
                self.urwid_browser.colview.browser.query(cmd_str)
                self.give_away_focus()
            elif self.active_command == 'add':
                if self.urwid_browser.colview.insert_column(cmd_str):
                    self.give_away_focus()
                else:
                    self.urwid_browser.modeline.set_text(str(cmd_str) + ' column not found in table browser')
            elif self.active_command == 'name current browser':
                self.urwid_browser.colview.name_current_browser(cmd_str)
                self.give_away_focus()
            elif self.active_command == 'switch to browser':
                self.urwid_browser.colview.switch_to_browser(None, cmd_str)
                self.give_away_focus()
        elif key == 'esc' or key == 'ctrl g':
            self.give_away_focus()
        elif key == 'ctrl c':
            # raise urwid.ExitMainLoop()
            self.give_away_focus()
        elif key == 'ctrl s':
            self._search(self.edit_text.get_edit_text(), True, True)
        elif key == 'ctrl r':
            self._search(self.edit_text.get_edit_text(), False, True)
        else:
            self.edit_text.keypress(size, key)
            if key != 'backspace':
                print('searching for', self.edit_text.get_edit_text())
                if self.active_command == 'search':
                    print('asking for forward search')
                    self._search(self.edit_text.get_edit_text(), True, False)
                elif self.active_command == 'search backward':
                    print('asking for backward search')
                    self._search(self.edit_text.get_edit_text(), False, False)


class SelectableText(urwid.Text):
    def __init__(self, text, align='right', wrap='clip', layout=None):
        # txt = text.strip()
        # try:
        #     i = float(txt)
        #     super(self.__class__, self).__init__(txt, 'right', wrap, layout)
        # except:
        super(self.__class__, self).__init__(text, align, wrap, layout)
    def selectable(self):
        return True # this allows us to assign focus to the columns of text
    # def keypress(self, size, key):
    #     return None


class UrwidColumnView(urwid.WidgetWrap):
    def __init__(self, urwid_frame):
        self.urwid_frame = urwid_frame
        self.urwid_cols = urwid.Columns([], dividechars=1)
        urwid.WidgetWrap.__init__(self, self.urwid_cols)

        self.browsers = dict()
        self.active_browser_name = None
        self.last_focused_column = dict()

    @property
    def browser(self):
        return self.browsers[self.active_browser_name]
    @property
    def focus_col(self):
        return self._col_by_index(self.focus_pos)
    @property
    def focus_pos(self):
        try:
            return self.urwid_cols.focus_position
        except:
            return self.last_focused_column[self.active_browser_name]
    def _col_by_index(self, idx):
        return self.browser.browse_columns[idx]

    # TODO break this into two functions - an 'add new' and a 'switch'
    # TODO this part of the code shouldn't know about Dataframes at all. remove all the actual switching logic into a separate class.
    def switch_to_browser(self, df, name=None):
        """Open an existing dataframe, or accept a new one."""
        print('switching to', name)
        i = len(self.browsers)
        while not name:
            name = 'df' + str(i)
            if name in self.browsers:
                i += 1
                name = None # keep trying til we find something valid
        if name not in self.browsers:
            print('making new browser')
            self.browsers[name] = DataframeBrowser(df)
            self.browsers[name].add_change_callback(self.update_view)
            self.last_focused_column[name] = 0
        self.active_browser_name = name
        del self.urwid_cols.contents[:]
        self.update_view()

    def name_current_browser(self, new_name):
        if new_name not in self.browsers.keys():
            browser = self.browsers.pop(self.active_browser_name)
            focus_column = self.last_focused_column.pop(self.active_browser_name)
            self.browsers[new_name] = browser
            self.last_focused_column[new_name] = focus_column
            self.active_browser_name = new_name

    def update_view(self, browser=None):
        try:
            print('updating view')
            display_browser_in_urwid_columns(self.urwid_cols, self.browser, self.focus_pos)
            self.update_text()
        except Exception as e:
            print('exception in update view', e)

    def update_text(self):
        self.urwid_frame.modeline.set_text(str(self.browser.view.selected_row_content(
            self.browser.browse_columns[self.urwid_cols.focus_position])))

    def scroll(self, num_rows):
        self.browser.view.scroll_rows(num_rows)
        self.update_view()

    def set_focus(self, col_num):
        col_num = max(0, min(col_num, len(self.urwid_cols.contents) - 1))
        try:
            focus_pos = self.urwid_cols.focus_position
            if self.urwid_cols.focus_position != col_num:
                set_attrib_on_col_pile(self.urwid_cols.contents[focus_pos][0], False)
                set_attrib_on_col_pile(self.urwid_cols.contents[col_num][0], True)
                self.urwid_cols.focus_position = col_num
                self.last_focused_column[self.active_browser_name] = col_num
                self.update_text()
            return True
        except Exception as e:
            print('exception in set focus' + e)
            return False

    def search_current_col(self, search_string, down=True, skip_current=False):
        if self.browser.search_column(self.focus_col, search_string, down, skip_current):
            self.update_view()
        else:
            # TODO could print help text saying the search failed.
            # TODO also, could potentially try wrapping the search just like emacs...
            pass

    def shift_col(self, shift_num):
        if self.browser.shift_column(self.urwid_cols.focus_position, shift_num):
            self.urwid_cols.focus_position += shift_num
            self.last_focused_column[self.active_browser_name] += shift_num
            self.update_view() # TODO this incurs a double update penalty but is necessary because the focus_position can't change until we know that the shift column was actually doable/successful

    def jump_to_col(self, num):
        num = num if num >= 0 else 9 # weird special case for when the input was a '0' key
        self.set_focus(num)

    def change_column_width(self, by_n):
        self.browser.view.change_column_width(self.focus_col, by_n)
        self.urwid_cols.contents[self.focus_pos] = (self.urwid_cols.contents[self.focus_pos][0],
                                                    _given(self.urwid_cols, self.browser.view.width(self.focus_col)))

    def sort_current_col(self, ascending=True):
        self.browser.sort_on_columns([self.focus_col], ascending=ascending)

    def mouse_event(self, size, event, button, col, row, focus):
        print(size, event, button, col, row, focus)
        return None
    # TODO make mouse events actually work? on columns they should definitely work.

    def insert_column(self, col_name, idx=None):
        try:
            if not idx or idx < 0 or idx > self.urwid_cols.focus_position:
                idx = self.urwid_cols.focus_position
        except Exception as e: # if for some reason cols.focus_position doesn't exist at all...
            print('exception in insert column', e)
            idx = 0
        return self.browser.insert_column(col_name, idx)

    def hide_current_col(self):
        return self.browser.hide_col_by_index(self.urwid_cols.focus_position)

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
            self.set_focus(self.urwid_cols.focus_position + 1)
        elif key in keybs('browse left'):
            self.set_focus(self.urwid_cols.focus_position - 1)
        elif key in keybs('browse down'):
            self.scroll(+1)
        elif key in keybs('browse up'):
            self.scroll(-1)
        elif key in keybs('undo'):
            self.browser.undo()
        elif key in keybs('quit'):
            raise urwid.ExitMainLoop()
        elif key in keybs('query'):
            self.urwid_frame.focus_minibuffer('query', column_name=self.focus_col)
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
        elif key in keybs('name current browser'):
            self.urwid_frame.focus_minibuffer('name current browser', default_text=self.active_browser_name)
        elif key in keybs('switch to browser'):
            self.urwid_frame.focus_minibuffer('switch to browser', completer=self._get_completer_with_hint(
                list(self.browsers.keys())))
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


# there really only ever needs to be one of these instantiated at a given time.
class UrwidDFBFrame:
    def __init__(self):
        self.modeline = Modeline()
        self.modeline.show_basic_commands()
        self.minibuffer = Minibuffer(self)
        self.colview = UrwidColumnView(self)
        self.inner_frame = urwid.Frame(urwid.Filler(self.colview, valign='top'),
                                       footer=urwid.AttrMap(self.modeline, 'modeline'))
        self.frame = urwid.Frame(self.inner_frame, footer=self.minibuffer)
    def browse(self, df, name=None):
        self.colview.switch_to_browser(df, name)
    def start(self):
        self.loop = urwid.MainLoop(self.frame, palette, # input_filter=self.input,
                                   unhandled_input=self.unhandled_input)
        self.loop.run()
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
def read_all_dfs_from_dir(directory):
    dataframes_and_names = list()
    for fn in os.listdir(directory):
        df = pd.DataFrame.from_csv(directory + os.sep + fn)
        name = fn[:-4]
        dataframes_and_names.append((df, name))
    return dataframes_and_names

def start_browser(dfs_and_names, df_name='dubois_mathlete_identities'):
    # st()
    global urwid_frame
    urwid_frame = UrwidDFBFrame()
    for df, name in dfs_and_names:
        urwid_frame.browse(df, name)
    urwid_frame.browse(None, df_name)
    urwid_frame.start()
    return urwid_frame

if __name__ == '__main__':
    # pd.set_option('display.max_rows', 9999)
    # pd.set_option('display.width', None)
    try:
        local_data = sys.argv[1]
        start_browser(read_all_dfs_from_dir(local_data))
    except (KeyboardInterrupt, EOFError) as e:
        print('\nLeaving the DuBois Project Data Explorer.')
