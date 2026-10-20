"""Local spelling hints from settled edits to a recent dictation span only."""
import json
from pathlib import Path
import re
import unicodedata
from typing import NamedTuple

MAX_SPAN = 2000


class Word(NamedTuple):
    text: str
    start: int
    end: int


def word_tokens(text):
    """Keep combining marks with their word, including non-Latin spellings."""
    def body(char):
        return char.isalnum() or char=='_' or unicodedata.category(char).startswith('M')
    index = 0
    while index<len(text):
        if not body(text[index]):
            index += 1
            continue
        start = index
        index += 1
        while index<len(text):
            if body(text[index]): index += 1
            elif text[index] in "'’-" and index+1<len(text) and body(text[index+1]): index += 1
            else: break
        yield Word(text[start:index],start,index)


def normalized_text(text):
    return text.replace('\r\n','\n').replace('\r','\n').replace('\u2028','\n').replace('\u2029','\n')


def valid_word(word):
    return (isinstance(word,str) and 2<=len(word)<=48
            and sum(char.isalpha() for char in word)>=2
            and sum(char.isdigit() for char in word)<=3
            and all(char.isalnum() or char in "_'’-" or unicodedata.category(char).startswith('M') for char in word)
            and (len(word)<24 or '_' not in word))


def corrected_words(before,after):
    """Only one-to-one word edits; additions/deletions are not spelling lessons."""
    old,new = list(word_tokens(before)),list(word_tokens(after))
    if len(old)!=len(new) or not old: return []
    changes = [(a,b) for a,b in zip(old,new) if a.text!=b.text]
    if len(changes)!=1: return []
    result = []
    for a,b in changes:
        source,word = a.text,b.text
        if source.casefold()==word.casefold(): continue
        if not valid_word(source) or not valid_word(word): return []
        # Exclude components of addresses, URLs and paths, not just their digits.
        for text,match in ((before,a),(after,b)):
            left,right = text[:match.start],text[match.end:]
            if (left and left[-1] in '@:/\\=') or (right and right[0] in '@:/\\='): return []
            if re.search(r'\w\.$',left) or re.match(r'\.\w',right): return []
        result.append(word)
    return list(dict.fromkeys(result))


class LearnedDictionary:
    LIMIT = 128

    def __init__(self,path):
        self.path = Path(path)
        self.words = []
        self.available = True
        if self.path.exists():
            try:
                if self.path.stat().st_size>65536: raise ValueError('Dictionary too large')
                data = json.loads(self.path.read_text(encoding='utf-8'))
                words = data['words']
                if data.get('version')!=1 or not isinstance(words,list) or len(words)>self.LIMIT or not all(valid_word(w) for w in words):
                    raise ValueError('Invalid dictionary')
                self.words = list(dict.fromkeys(words))
            except (OSError,ValueError,KeyError,TypeError):
                self.available = False  # Preserve a damaged file instead of overwriting it.

    def save_words(self,words):
        if not self.available: raise OSError('Local dictionary unavailable')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps({'version':1,'words':words},ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(self.path)
        self.words = words

    def add(self,words):
        existing = {word.casefold() for word in self.words}
        added = []
        for word in words:
            if valid_word(word) and word.casefold() not in existing:
                added.append(word);existing.add(word.casefold())
        if added: self.save_words((self.words+added)[-self.LIMIT:])
        return added

    def remove(self,words):
        remove = set(words)
        self.save_words([word for word in self.words if word not in remove])

    def vocabulary(self,manual):
        result,seen = [],set()
        for word in [*manual,*reversed(self.words)]:
            if word.casefold() in seen: continue
            if len(result)>=32 or len(', '.join([*result,word]).encode('utf-8'))>2000: break
            result.append(word);seen.add(word.casefold())
        return result


class EditSession:
    """In-memory baseline; never writes transcript text to the dictionary."""
    def __init__(self,text,now):
        self.baseline = self.last = normalized_text(text)
        self.deadline = now+60
        self.changed_at = now
        self.active = 0<len(self.baseline)<=MAX_SPAN

    def observe(self,text,now):
        if not self.active or now>=self.deadline or not isinstance(text,str) or len(text)>MAX_SPAN:
            self.active = False
            return []
        text = normalized_text(text)
        if text!=self.last:
            self.last,self.changed_at = text,now
            return []
        if text==self.baseline or now-self.changed_at<2: return []
        learned = corrected_words(self.baseline,text)
        # Do not treat a later appended sentence as part of this dictation.
        if not learned and [m.text.casefold() for m in word_tokens(text)]!=[m.text.casefold() for m in word_tokens(self.baseline)]:
            self.active = False
        self.baseline = text
        return learned
