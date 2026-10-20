"""Source-grounded enumeration layout; generated boundaries never add words."""
import json
import re

# Boundary hints for common technical multiword names, plus the user's vocabulary.
# These affect layout only, never ASR spelling or words in ordinary paragraphs.
TECH_NAMES = ('lang graph','lang chain','power bi','scikit learn','visual studio code',
              'python','sql','excel','numpy','pandas','matplotlib','pytorch','tensorflow',
              'javascript','typescript','postgresql','mysql','sqlite','react','fastapi',
              'whisper','qwen','pyside6')
INTRO = re.compile(r'\b(?:tools|technologies|libraries|frameworks|features|requirements|dependencies|ingredients|components|options|tasks|steps|items|examples|outputs|deliverables)\s+(?:such\s+as|including|like|are|include|includes|consist\s+of|comprise)\s*:?\s*',re.I)
TRANSITION = re.compile(r'\b(?:the\s+(?:(?:basic|main|primary)\s+)?(?:use|purpose|goal|reason)|(?:this|the)\s+(?:app|application|project)\s+(?:will|is|can|takes)|it\s+(?:will|can|takes|runs|does|gives|produces))\b',re.I)
ORDINALS = ('first','second','third','fourth','fifth','sixth','seventh','eighth','ninth','tenth')
ORDINAL = re.compile(r'\b(?:and\s+)?(?:the\s+)?(?P<index>'+ '|'.join(ORDINALS) +r')(?:(?:\s+(?:one|item|output|file|report|pdf|step|point))|ly)(?:\s+(?:will\s+be|would\s+be|should\s+be|is|are))?\s*[:,]?\s*',re.I)
QUOTED = re.compile(r'```[\s\S]*?```|`[^`]*`|"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)')
LIST_COMMAND = re.compile(r'\b(?:(?:make|create|start|begin)\s+)?(?:a\s+)?(?P<style>bullet(?:ed)?|numbered)\s+list\b[\s.,:;]*',re.I)
END_LIST = re.compile(r'\b(?:end|finish)\s+(?:the\s+)?list\b[\s.,:;]*',re.I)
EXPLICIT_ITEM = re.compile(r'\b(?:(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:point|item)|next\s+(?:bullet\s+)?(?:point|item)|bullet\s+point|number\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+))\b[\s.,:;]*',re.I)
CONNECTORS = re.compile(r'\b(?:and|or|plus|as\s+well\s+as)\b|[,;&]',re.I)
ACTION = (r'(?:fix|make|check|test|improve|update|verify|confirm|send|explain|share|review|'
          r'collect|install|remove|ensure|run|open|select|finish|keep|pay|meet|call|buy|'
          r'add|create|write|build|prepare|compare|download|save|delete|restart|enable|disable)')
ACTION_START = re.compile(r'^(?:(?:please|could\s+you|can\s+you)\s+)?'+ACTION+r'\b',re.I)
TASK_INTRO = re.compile(r'\b(?:(?:we|you|I)\s+(?:also\s+)?(?:need|have|want)\s+to|'
                        r'(?:tasks|steps|requests|requirements)\s+(?:are|include)|'
                        r'(?:a\s+few|some|several)\s+things\s+I\s+need\s+from\s+you)\s*[.:]?\s*',re.I)
INLINE_CATEGORIES = {'tools','technologies','libraries','frameworks','dependencies',
                     'ingredients','components','options','examples'}
IGNORED_WORDS = set(('the a an and or for that this with will would should first second third fourth fifth '
                     'sixth seventh eighth ninth tenth one are was were such okay then um uh basically '
                     'actually really just so is am be been being it its to of in on at as by from '
                     'I we you my our your have has had do does did can could there here').lower().split())


def content_words(text):
    text=re.sub(r"n['’]t\b",' not',text,flags=re.I)
    text=re.sub(r"['’](?:m|re|ve|ll|d|s)\b",'',text,flags=re.I)
    return {word.casefold() for word in re.findall(r'[^\W_]+',text)
            if len(word)>1 and word.casefold() not in IGNORED_WORDS}


def word_coverage(source,result):
    words=content_words(source)
    target=content_words(result)
    # Only known technical names may bridge token boundaries. Substring matches
    # such as 'report' inside 'reportedly' must not count as preserved content.
    for name in TECH_NAMES:
        if re.search(r'(?<!\w)'+literal_pattern(name)+r'(?!\w)',result,re.I):target.update(content_words(name))
    return len(words&target)/len(words) if words else 1


def action_items(source):
    """Only split parallel actions, never arbitrary comma-heavy prose.

    Decimal/currency commas, quoted strings and code are literal. Conjunctions
    inside an action stay there unless another action begins after them.
    """
    protected=[m.span() for m in QUOTED.finditer(source)]
    protected += [m.span() for m in re.finditer(r'\d[,.]\d',source)]
    protected += [m.span() for m in re.finditer(r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},\s*\d{4}\b',source,re.I)]
    cuts=[]
    separator=re.compile(r',|;|\band\s+(?=(?:(?:please|could\s+you|can\s+you)\s+)?'+ACTION+r'\b)',re.I)
    for match in separator.finditer(source):
        if any(a<match.end() and match.start()<b for a,b in protected):continue
        # Parenthesized arguments must never become action boundaries.
        prefix=source[:match.start()]
        if any(prefix.count(a)!=prefix.count(b) for a,b in ('()','[]','{}')):continue
        cuts.append(match.span())
    pieces=[];offset=0
    for start,end in [*cuts,(len(source),len(source))]:
        piece=source[offset:start].strip(' \t\r\n,;')
        piece=re.sub(r'^and\s+','',piece,flags=re.I)
        if piece:pieces.append(piece)
        offset=end
    if len(pieces)<3 or any(not ACTION_START.match(piece) or len(piece)>400 for piece in pieces):return []
    # A later sentence belongs to the explanation, not the last action.
    if any(re.search(r'[.!?]\s+\S',piece) for piece in pieces):return []
    return pieces


class Passage(str):
    """Marks final context blocks; previews keep the existing sentence flow."""


def literal_pattern(text):
    return r'\s*'.join(re.escape(char) for char in text if not char.isspace())


def checked_items(source,proposed):
    if not isinstance(proposed,list) or not 2<=len(proposed)<=24:return []
    items=[];offset=0
    for item in proposed:
        if not isinstance(item,str) or not item.strip() or len(item)>400:return []
        if not CONNECTORS.sub('',item).strip(' \t\r\n.,:!?'):return []
        match=re.search(literal_pattern(item),source[offset:],re.I)
        if not match:return []
        start,end=offset+match.start(),offset+match.end()
        if CONNECTORS.sub('',source[offset:start]).strip(' \t\r\n.,:!?'):return []
        items.append(source[start:end]);offset=end
    if CONNECTORS.sub('',source[offset:]).strip(' \t\r\n.,:!?'):return []
    return items


def known_items(source,vocabulary):
    names=sorted({name for name in (*TECH_NAMES,*vocabulary) if isinstance(name,str) and name.strip()},key=len,reverse=True)
    matches=[]
    for name in names:
        for match in re.finditer(r'(?<!\w)'+literal_pattern(name)+r'(?!\w)',source,re.I):
            if not any(a<match.end() and match.start()<b for a,b in matches):matches.append(match.span())
    if len(matches)<2:return []
    matches.sort();items=[];offset=0
    for start,end in [*matches,(len(source),len(source))]:
        gap=source[offset:start]
        fragments=[part.strip(' \t\r\n.,:!?') for part in CONNECTORS.split(gap)]
        if any(len(part.split())>3 or re.search(r'\b(?:because|when|while|which|that|will|would|does|was|were)\b',part,re.I) for part in fragments if part):return []
        items.extend(part for part in fragments if part)
        if start<end:items.append(source[start:end])
        offset=end
    return checked_items(source,items)


def item_prompt(source,category):
    safe=source.replace('<|','‹|').replace('|>','|›')
    return ('<|im_start|>system\nSeparate the '+category+' enumeration into individual items. '
            'Return only a JSON array of source strings. Keep multiword names together. '
            'Copy every source item in order, excluding conjunctions. Never add words. /no_think<|im_end|>\n'
            '<|im_start|>user\nred apples, green pears and ripe plums<|im_end|>\n'
            '<|im_start|>assistant\n["red apples","green pears","ripe plums"]<|im_end|>\n'
            '<|im_start|>user\n'+safe+'<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n')


def prepare_layout(raw,splitter=None,vocabulary=()):
    """Return source words with locally verified list boundaries and item anchors."""
    protected=[match.span() for match in QUOTED.finditer(raw)]
    def quoted(start,end):return any(a<end and start<b for a,b in protected)
    changes=[];anchors=[];model_requests=0
    commands=[m for m in LIST_COMMAND.finditer(raw) if not quoted(*m.span())]
    for index,command in enumerate(commands):
        end=commands[index+1].start() if index+1<len(commands) else len(raw)
        stop=next((m for m in END_LIST.finditer(raw,command.end(),end) if not quoted(*m.span())),None)
        if stop:end=stop.start()
        markers=[m for m in EXPLICIT_ITEM.finditer(raw,command.end(),end) if not quoted(*m.span())]
        if not markers:continue
        if not stop:
            # Without an explicit End list, leave a following sentence as prose.
            sentence=re.search(r'[.!?](?=\s+[A-Z]|\s*$)',raw[markers[-1].end():end])
            if sentence:end=markers[-1].end()+sentence.end()
        items=[]
        lead=raw[command.end():markers[0].start()].strip(' \t\r\n.,:;')
        if lead:items.append((command.end(),lead))
        items.extend((m.end(),raw[m.end():(markers[n+1].start() if n+1<len(markers) else end)].strip(' \t\r\n,;'))
                     for n,m in enumerate(markers))
        if any(not item for _,item in items):continue
        bullet=command['style'].lower().startswith('bullet')
        text='\n\n'+'\n'.join(('- ' if bullet else f'{n}. ')+item for n,(_,item) in enumerate(items,1))+'\n\n'
        changes.append((command.start(),stop.end() if stop else end,text))
        anchors.extend(items)
    ordinals=[match for match in ORDINAL.finditer(raw) if not quoted(*match.span())]
    i=0
    while i<len(ordinals):
        first=ordinals[i]
        if any(a<=first.start()<b for a,b,_ in changes):i+=1;continue
        if first['index'].lower()!='first':i+=1;continue
        group=[first];starts=[first.start()];j=i+1
        while j<len(ordinals):
            previous=group[-1];current=ordinals[j]
            a,b=ORDINALS.index(previous['index'].lower()),ORDINALS.index(current['index'].lower())
            if b==a and not raw[previous.end():current.start()].strip(' \t\r\n.,:;'):
                group[-1]=current;j+=1;continue  # Repeated empty false start.
            if b!=a+1:break
            group.append(current);starts.append(current.start());j+=1
        if len(group)<2:i+=1;continue
        last_end=ordinals[j].start() if j<len(ordinals) else len(raw)
        tail=raw[group[-1].end():last_end]
        sentence=re.search(r'[.!?](?=\s+[A-Z]|\s*$)',tail)
        if sentence:last_end=group[-1].end()+sentence.end()
        items=[raw[m.end():(starts[n+1] if n+1<len(group) else last_end)].strip(' \t\r\n,;') for n,m in enumerate(group)]
        if all(items):
            start=first.start()
            styles=[m for m in re.finditer(r'\b(?:(bullet(?:ed)?|numbered)\s+list|end\s+list)\b',raw[:start],re.I) if not quoted(*m.span())]
            bullet=bool(styles and (styles[-1][1] or '').lower().startswith('bullet'))
            lines=[('- ' if bullet else f'{n}. ')+item for n,item in enumerate(items,1)]
            changes.append((start,last_end,'\n\n'+'\n'.join(lines)+'\n\n'))
            anchors.extend((match.end(),item) for match,item in zip(group,items))
        i=j
    intros=sorted([*INTRO.finditer(raw),*TASK_INTRO.finditer(raw)],key=lambda m:m.start())
    for intro in intros:
        start=intro.end()
        if quoted(intro.start(),start) or any(a<=start<b for a,b,_ in changes):continue
        tail=raw[start:];end=len(raw)
        transition=TRANSITION.search(tail)
        sentence=re.search(r'[.!?](?=\s|$)',tail)
        if transition:end=min(end,start+transition.start())
        if sentence:end=min(end,start+sentence.end())
        if any(a<end and start<b for a,b,_ in changes):continue
        source=raw[start:end].strip()
        if not source or len(source.encode('utf-8'))>700 or quoted(start,end):continue
        if re.search(r'[()\[\]{}=]|\d[,.:/\-]\d|[$₹€£¥]\s*\d',source):continue
        category=intro.group().split()[0].lower()
        # Names and groceries usually belong in the sentence. Add separators
        # to confidently identified, unpunctuated names without inventing words.
        if category in INLINE_CATEGORIES:
            items=known_items(source,vocabulary)
            if len(items)>=3 and ',' not in source:
                suffix='.' if source.endswith('.') else ''
                boundary=bool(transition and start+transition.start()==end)
                changes.append((start,end,', '.join(items)+(suffix or ('.' if boundary else ''))+('\n\n' if boundary else ' ')))
            continue
        task=bool(TASK_INTRO.fullmatch(intro.group()))
        items=action_items(source) if task else known_items(source,vocabulary)
        if task and not items:continue
        if not items:
            parts=[x.strip(' \t\r\n.,!?') for x in CONNECTORS.split(source) if x.strip(' \t\r\n.,!?')]
            if len(parts)>=3:items=checked_items(source,parts)
        if not items and splitter and model_requests<2 and not TASK_INTRO.fullmatch(intro.group()):
            model_requests+=1
            try:items=checked_items(source,json.loads(splitter(item_prompt(source,intro.group().split()[0]))))
            except (ValueError,TypeError):items=[]
        if len(items)<3:continue
        list_start=start
        while list_start and raw[list_start-1] in ' \t':list_start-=1
        list_end=end
        while list_end<len(raw) and raw[list_end] in ' \t':list_end+=1
        colon='' if list_start and raw[list_start-1]==':' else ':'
        changes.append((list_start,list_end,colon+'\n'+'\n'.join('- '+item for item in items)+'\n\n'))
        offset=start
        for item in items:
            position=raw.find(item,offset);anchors.append((position,item));offset=position+len(item)
    result=raw
    for start,end,text in sorted(changes,reverse=True):result=result[:start]+text+result[end:]
    return result.strip(),[item for _,item in sorted(anchors)]


def layout_retained(prepared,result,anchors):
    def items(text):
        return [match[1] for line in text.splitlines() if (match:=re.match(r'^\s*(?:[-*•]|\d+[.)])\s+(.*\S)',line))]
    output_items=items(result)
    if len(items(prepared))!=len(output_items):return False
    if word_coverage(prepared,result)<.8:return False
    offset=0
    for item in anchors:
        found=next((i for i in range(offset,len(output_items)) if word_coverage(item,output_items[i])>=.8),None)
        if found is None:return False
        offset=found+1
    # Closing explanations must remain prose, rather than being swallowed by
    # the last item. This also catches summaries that retain only list words.
    outside=' '.join(line for line in prepared.splitlines()
                     if not re.match(r'^\s*(?:[-*•]|\d+[.)])\s+',line))
    output_outside=' '.join(line for line in result.splitlines()
                            if not re.match(r'^\s*(?:[-*•]|\d+[.)])\s+',line))
    if word_coverage(outside,output_outside)<.7:return False
    return True
