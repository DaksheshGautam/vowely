"""Local spelling hints from edits to a recently dictated draft."""
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata
from typing import NamedTuple

MAX_SPAN = 12000


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


def corrected_words(before,after,scope=None):
    """Align drafts; learn replacements in dictated text, never pure additions."""
    old,new = list(word_tokens(before)),list(word_tokens(after))
    result = []
    def eligible(text,match):
        if not valid_word(match.text): return False
        left,right = text[:match.start],text[match.end:]
        if (left and left[-1] in '@:/\\=') or (right and right[0] in '@:/\\='): return False
        return not (re.search(r'\w\.$',left) or re.match(r'\.\w',right))
    aligned = SequenceMatcher(None,[w.text.casefold() for w in old],
                              [w.text.casefold() for w in new],autojunk=False)
    for kind,a,b,c,d in aligned.get_opcodes():
        if kind!='replace': continue
        source,changed = old[a:b],new[c:d]
        if not source or not changed or len(changed)>24: continue
        if scope and any(w.start<scope[0] or w.end>scope[1] for w in source): continue
        # Unequal token counts can mean split/merged names, or newly added prose.
        # Accept only blocks with similar combined spelling in that case.
        if len(source)==len(changed): pairs = list(zip(source,changed))
        elif SequenceMatcher(None,''.join(w.text.casefold() for w in source),
                             ''.join(w.text.casefold() for w in changed),autojunk=False).ratio()>=.68:
            pairs = [(source[0],w) for w in changed]
        else:
            # A tail correction and an appended sentence share one diff block.
            # Match close spellings only; never learn every appended word.
            pairs,offset = [],0
            for original in source:
                scores = [(SequenceMatcher(None,original.text.casefold(),w.text.casefold(),autojunk=False).ratio(),i,w)
                          for i,w in enumerate(changed[offset:],offset)]
                if not scores: break
                ratio,index,word = max(scores,key=lambda item:item[0])
                if ratio>=.68:
                    pairs.append((original,word));offset=index+1
        for original,replacement in pairs:
            if not eligible(before,original) or not eligible(after,replacement): continue
            if original.text.casefold()!=replacement.text.casefold(): result.append(replacement.text)
    return list(dict.fromkeys(result))[:24]


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
    """Compare the last draft on completion; typing never starts a save timer."""
    def __init__(self,text,now,scope=None):
        self.baseline = self.last = normalized_text(text)
        self.scope = scope
        self.deadline = now+600
        self.active = 0<len(self.baseline)<=MAX_SPAN

    def observe(self,text,now):
        if not self.active or now>=self.deadline or not isinstance(text,str) or len(text)>MAX_SPAN:
            self.active = False
            return []
        text = normalized_text(text)
        if not text.strip(): return self.finish()
        self.last = text
        return []

    def finish(self):
        if not self.active: return []
        self.active = False
        words = corrected_words(self.baseline,self.last,self.scope)
        self.baseline = self.last = ''
        return words
