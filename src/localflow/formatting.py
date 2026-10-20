"""Transcript layout rules and conservative checks for generated numbering."""
import re
from .natural_layout import Passage,INTRO,ORDINAL,prepare_layout,action_items,QUOTED


LAYOUT_CUE = re.compile(
    r'\b(?:(?:(?:make|create|start|begin)\s+)?(?:a\s+)?(?:bulleted|bullet|numbered)\s+list'
    r'|(?:bullet\s+point|next\s+(?:bullet\s+)?(?:point|item)|(?:new|next|start\s+a|begin\s+a)\s+paragraph|(?:new|next|blank)\s+line|paragraph\s+break)'
    r'|(?:first|second|third|fourth|fifth)\s+(?:point|item)'
    r'|number\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)'
    r'|(?:end|finish)\s+(?:the\s+)?list)\b',re.IGNORECASE)

# Decimal amounts, dates, times, signs, currency and numeric identifiers retain
# their literal form. Whitespace inside a currency/percentage token may change.
NUMBER = re.compile(r'[+\-−]?(?:[$₹€£¥]\s*)?[+\-−]?\d+(?:[.,:/\-]\d+)*(?:\s*%)?')
LIST_MARKER = re.compile(r'(?m)^[ \t]{0,3}(\d{1,3})[.)][ \t]+(?=\S)')
LIST_LINE = re.compile(r'^[ \t]{0,3}(?:[-*•]|\d{1,3}[.)])[ \t]+\S')
SPOKEN_INDEX = re.compile(r'(?:^|[.!?;:]\s*)number\s+(\d{1,2})\b',re.IGNORECASE)
ITEM_CUE = (r'(?:(?:first|second|third|fourth|fifth)\s+(?:point|item)'
            r'|next\s+(?:bullet\s+)?(?:point|item)|bullet\s+point'
            r'|number\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+))')

FORMAT_INSTRUCTIONS = (
    ' Use actual newline characters and blank lines between topics. Group related sentences into paragraphs. Keep ordinary names, tools, groceries '
    'and narrative actions in sentences; commas alone never request bullets. Use bullets for distinct tasks '
    'or requests, and numbered lists for consecutive first/second/third descriptions. Keep every item, '
    'multiword name, introduction and closing explanation. Preserve supplied list boundaries. '
    'Honor spoken bullet/numbered list, first/next point or item, number one/two and end list commands. '
    'New/next/start a/begin a paragraph, paragraph break and blank line mean a blank line; new/next line means one break. '
    'Remove these formatting commands. Keep content numbers, amounts, signs, currencies, dates, times, '
    'phone numbers and identifiers exactly; do not convert number words to digits except item labels. '
    'Quoted text and code stay literal. No headings, commentary or invented facts.'
)


def has_layout_cues(text):
    return bool(LAYOUT_CUE.search(text))


def finish_natural_text(text):
    """Finish obvious repeats and explicit same-verb corrections locally.

    Three to twelve words, on one line only. Quoted/code text, digit-containing
    phrases, identifiers and spelled-out number sequences are kept literal.
    Same-verb "no, I mean" restarts are resolved only without a negative prefix
    or numeric revision. No paraphrases or nonadjacent repeats are guessed away.
    """
    repeated=re.compile(r"\b(?P<phrase>[\w’'-]+(?:[ \t]+[\w’'-]+){2,11})[ \t]*[,.;!?]?[ \t]+(?P=phrase)\b",re.I)
    restart=re.compile(r"\b(?P<verb>cancel|send|schedule|use|buy|delete|keep|open|select|install|update)\s+"
                       r"(?:[\w’'-]+[ \t]+){0,7}[\w’'-]+[ \t]*,?[ \t]*"
                       r"(?:no[ \t]*,?[ \t]*I[ \t]+mean|sorry[ \t]*,?[ \t]*I[ \t]+mean)[ \t]+(?P=verb)\b",re.I)
    numbers=set('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion'.split())
    def clean(part):
        def correct(match):
            prefix=part[max(0,match.start()-60):match.start()]
            if (any(char.isdigit() or char=='_' for char in match.group())
                    or re.search(r"\b(?:not|never|cannot|without|repeat|literal|password|code)\b|n['’]t\b",prefix,re.I)):
                return match.group()
            return match['verb']
        # Only an explicit restart of the same verb is resolved locally. Keep
        # negative prefixes and numeric revisions untouched for normal review.
        part=restart.sub(correct,part)
        def replace(match):
            phrase=match['phrase'];words=phrase.casefold().split()
            if any(char.isdigit() or char=='_' for char in phrase) or all(word in numbers for word in words):return match.group()
            # Literal rehearsal, even without quotation marks, stays literal.
            if re.search(r'\b(?:repeat|repeated|exactly|literal|password|code)\b',part[max(0,match.start()-60):match.start()],re.I):return match.group()
            return phrase
        for _ in range(8):
            revised=repeated.sub(replace,part)
            if revised==part:break
            part=revised
        return part
    result=[];offset=0
    for literal in QUOTED.finditer(text):
        result.extend((clean(text[offset:literal.start()]),literal.group()));offset=literal.end()
    result.append(clean(text[offset:]))
    return ''.join(result)


def final_cleanup_blocks(text,limit=2500):
    """Give final cleanup passage context while respecting the small model budget."""
    blocks=[];remaining=text.strip()
    while len(remaining.encode('utf-8'))>limit:
        prefix=remaining.encode('utf-8')[:limit].decode('utf-8',errors='ignore')
        boundaries=list(re.finditer(r'\n[ \t]*\n|[.!?।。！？]\s+',prefix))
        cut=boundaries[-1].end() if boundaries else prefix.rfind(' ')
        if cut<=0:break  # Preserve oversized identifiers/code instead of cutting them.
        blocks.append(Passage(remaining[:cut].strip()));remaining=remaining[cut:].lstrip()
    if remaining:blocks.append(Passage(remaining))
    return blocks


def comma_list_items(text):
    """Compatibility helper for a standalone enumeration of parallel actions.

    A comma count no longer decides layout. Ordinary prose and names stay
    inline; mixed passages are prepared by the contextual layout adapter.
    """
    if has_layout_cues(text) or INTRO.search(text) or len(list(ORDINAL.finditer(text)))>=2 or any(LIST_LINE.match(line) for line in text.splitlines()):
        return []
    return action_items(text)


def comma_list_text(items):
    return '\n'.join('- '+item for item in items)


def ensure_comma_list(raw,result):
    """Keep the requested layout even when the small model returns prose."""
    items = comma_list_items(raw)
    if not items: return result
    lines = [line for line in result.splitlines() if line.strip()]
    if len(lines)==len(items) and all(re.match(r'^\s*[-*•]\s+\S',line) for line in lines):
        return result
    edited_items = comma_list_items(result)
    # If cleanup merged boundaries, retain the source rather than guess items.
    return comma_list_text(edited_items if len(edited_items)==len(items) else items)


class PreservedCleanupNotice(str):
    """Local adapter returned source words rather than a rejected model edit."""


def preserved_cleanup(raw,warning):
    """A model failure can still apply layout without rewriting any words."""
    text = ensure_comma_list(raw,apply_layout_cues(raw,prepare_layout(raw)[0]))
    if text!=raw:
        warning += (' Local comma-list formatting applied; review required.' if comma_list_items(raw)
                    else ' Local source-layout formatting applied; review required.')
    return text,PreservedCleanupNotice(warning)


def content_length(text):
    """Layout commands can legitimately disappear without deleting content."""
    return len(LAYOUT_CUE.sub('',text).strip(' \t\r\n.,:;'))


def numbers(text):
    return [re.sub(r'\s+','',match.group()) for match in NUMBER.finditer(text)]


def numbers_preserved(raw,result):
    original = numbers(raw)
    if original==numbers(result): return True
    markers = list(LIST_MARKER.finditer(result))
    if not markers: return False
    # Only a coherent ordered list is structural. Arbitrary leading numbers,
    # decimals, nonsequential markers and numeric content are never ignored.
    expected=1;previous=None;runs=[];run=0
    for marker in markers:
        value=int(marker.group(1))
        if previous and value==1 and re.search(r'\n[ \t]*\n',result[previous.start():marker.start()]):
            runs.append(run);run=0;expected=1
        if value!=expected:return False
        expected+=1;run+=1;previous=marker
    runs.append(run)
    if 1 in runs and not has_layout_cues(raw): return False
    without_markers = LIST_MARKER.sub('',result)
    if original==numbers(without_markers): return True
    # ASR may write "number 1" rather than "number one". Only consecutive
    # explicit item labels at sentence starts may move into list markers.
    labels = list(SPOKEN_INDEX.finditer(raw))
    if not labels:return False
    available=iter(int(m.group(1)) for m in markers)
    if not all(any(value==int(label.group(1)) for value in available) for label in labels):return False
    parts,offset = [],0
    for label in labels:
        parts.append(raw[offset:label.start(1)])
        offset = label.end(1)
    parts.append(raw[offset:])
    return numbers(''.join(parts))==numbers(without_markers)


def apply_layout_cues(raw,text):
    """Finish explicit layout instructions a small cleanup model may leave in.

    Quoted text/code stays literal. List cue removal is restricted to the start
    of actual output items; payload numbers are validated afterward.
    """
    if not has_layout_cues(raw): return text
    text = text.replace('\r\n','\n')
    quoted = re.compile(r'```[\s\S]*?```|`[^`]*`|"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)')
    spans = [match.span() for match in quoted.finditer(text)]
    def paragraph(match):
        if any(start<=match.start()<end for start,end in spans): return match.group()
        return '\n' if match.group(1).lower() in ('new line','next line') else '\n\n'
    text = re.sub(r'[ \t]*\b((?:new|next|start\s+a|begin\s+a)\s+paragraph|paragraph\s+break|(?:new|next|blank)\s+line)\b[ \t]*[.,:;!?]?[ \t]*',paragraph,text,flags=re.IGNORECASE)
    text = re.sub(r'(?m)^([ \t]{0,3}(?:[-*•]|\d{1,3}[.)])[ \t]+)'+ITEM_CUE+r'\b[ \t.,:;\-]*',r'\1',text,flags=re.IGNORECASE)
    text = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+','\n\n',text)
    return '\n'.join(line.rstrip() for line in text.split('\n')).strip()


def join_blocks(blocks):
    """Preserve multiline cleanup when sentences are assembled for preview/copy."""
    result = ''
    for block in blocks:
        block = block.strip()
        if not block: continue
        separator = '\n' if ('\n' in result or '\n' in block or LIST_LINE.match(block) or LIST_LINE.match(result)) else ' '
        result = result+separator+block if result else block
    return result
