import urwid
import sys

class AdvancedEdit(urwid.Edit):
    """Edit box with some custom improvments
    new chars:
              - C-a: like 'home'
              - C-e: like 'end'
              - C-k: remove everything on the right of the cursor
              - C-w: remove the word on the back
    """
  
    def setCompletionMethod(self, callback):
        """Define method called when completion is asked
        @callback: method with 2 arguments:
                    - the text to complete
                    - if there was already a completion, a dict with
                        - 'completed':last completion
                        - 'completion_pos': cursor position where the completion starts
                        - 'position': last completion cursor position
                      this dict must be used (and can be filled) to find next completion)
                   and which return the full text completed"""
        self.completion_cb = callback
        self.completion_data = {}
  
    def keypress(self, size, key):
        if key == 'ctrl a':
            key = 'home'
        elif key == 'ctrl e':
            key = 'end'
        elif key == 'ctrl k':
            self._delete_highlighted()
            self.set_edit_text(self.edit_text[:self.edit_pos])
        elif key == 'ctrl w':
            before = self.edit_text[:self.edit_pos]
            pos = before.rstrip().rfind(" ")+1
            self.set_edit_text(before[:pos] + self.edit_text[self.edit_pos:])
            self.set_edit_pos(pos)
        elif key == 'tab':
            try:
                before = self.edit_text[:self.edit_pos]
                if self.completion_data:
                    if (not self.completion_data['completed']
                        or self.completion_data['position'] != self.edit_pos
                        or not before.endswith(self.completion_data['completed'])):
                        self.completion_data.clear()
                    else:
                        before = before[:-len(self.completion_data['completed'])]
                complet = self.completion_cb(before, self.completion_data)
                self.completion_data['completed'] = complet[len(before):]
                self.set_edit_text(complet+self.edit_text[self.edit_pos:])
                self.set_edit_pos(len(complet))
                self.completion_data['position'] = self.edit_pos
                return
            except AttributeError:
                #No completion method defined
                pass
        rval = super(AdvancedEdit, self).keypress(size, key)
        return rval


class ListCompleter:
    def __init__(self, words, hint=sys.stdout.write):
        self.words = sorted(words) # a list of words that are 'valid'
        self.hint = hint
    def complete(self, prefix, completion_data):
        try:
            start_idx = self.words.index(completion_data['last']) + 1
            if start_idx == len(self.words):
                start_idx = 0
        except (KeyError,ValueError):
            start_idx = 0

        options = [word if word.startswith(prefix) else '' for word in self.words]
        self.hint('options: ' + ' '.join(str(t) + ' ' for t in options))

        for idx in range(start_idx, len(self.words)) + range(0, start_idx):
            if self.words[idx].lower().startswith(prefix):
                completion_data['last'] = self.words[idx]
                return self.words[idx]
        return prefix