# this class exists so we can use readline for our prompt
# this is stolen from http://stackoverflow.com/questions/18369207/python-user-input-replay
class Completer:
    def __init__(self, words):
        self.words = words
        self.prefix = None
    def complete(self, prefix, index):
        if prefix != self.prefix:
            # we have a new prefix!
            # find all words that start with this prefix
            self.matching_words = [
                w for w in self.words if w.startswith(prefix)
                ]
            self.prefix = prefix
        try:
            return self.matching_words[index]
        except IndexError:
            return None

