"""Source-grounded enumeration layout; generated boundaries never add words."""
import json
import re

# Boundary hints for common technical multiword names, plus the user's vocabulary.
# These affect layout only, never ASR spelling or words in ordinary paragraphs.
TECH_NAMES = ('lang graph','lang chain','power bi','scikit learn','visual studio code',
              'python','sql','excel','numpy','pandas','matplotlib','pytorch','tensorflow',
              'javascript','typescript','postgresql','mysql','sqlite','react','fastapi')
INTRO = re.compile(r'\b(?:tools|technologies|libraries|frameworks|features|requirements|dependencies|ingredients|components|options|tasks|steps|items|examples|outputs|deliverables)\s+(?:such\s+as|including|like|are|include|includes|consist\s+of|comprise)\s*:?\s*',re.I)
TRANSITION = re.compile(r'\b(?:the\s+(?:(?:basic|main|primary)\s+)?(?:use|purpose|goal|reason)|(?:this|the)\s+(?:app|application|project)\s+(?:will|is|can|takes)|it\s+(?:will|can|takes|runs|does|gives|produces))\b',re.I)
ORDINALS = ('first','second','third','fourth','fifth','sixth','seventh','eighth','ninth','tenth')
ORDINAL = re.compile(r'\b(?:and\s+)?(?:the\s+)?(?P<index>'+ '|'.join(ORDINALS) +r')(?:(?:\s+(?:one|item|output|file|report|pdf|step|point))|ly)(?:\s+(?:will\s+be|would\s+be|should\s+be|is|are))?\s*[:,]?\s*',re.I)
QUOTED = re.compile(r'```[\s\S]*?```|`[^`]*`|"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)')
CONNECTORS = re.compile(r'\b(?:and|or|plus|as\s+well\s+as)\b|[,;&]',re.I)


class Passage(str):
    """Marks final context blocks; previews keep the existing sentence flow."""


def literal_pattern(text):
    return r'\s*'.join(re.escape(char) for char in text if not char.isspace())


def checked_items(source,proposed):
    if not isinstance(proposed,list) or not 2<=len(proposed)<=24:return []
    items=[];offset=0
    for item in proposed:
        if not isinstance(item,str) or not item.strip() or len(item)>100:return []
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
    ordinals=[match for match in ORDINAL.finditer(raw) if not quoted(*match.span())]
    i=0
    while i<len(ordinals):
        first=ordinals[i]
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
            changes.append((start,last_end,'\n\n'+'\n'.join(f'{n}. '+item for n,item in enumerate(items,1))+'\n\n'))
            anchors.extend((match.end(),item) for match,item in zip(group,items))
        i=j
    for intro in INTRO.finditer(raw):
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
        items=known_items(source,vocabulary)
        if not items:
            parts=[x.strip(' \t\r\n.,!?') for x in CONNECTORS.split(source) if x.strip(' \t\r\n.,!?')]
            if len(parts)>=3:items=checked_items(source,parts)
        if not items and splitter and model_requests<2:
            model_requests+=1
            try:items=checked_items(source,json.loads(splitter(item_prompt(source,intro.group().split()[0]))))
            except (ValueError,TypeError):items=[]
        if len(items)<3:continue
        changes.append((start,end,'\n'+'\n'.join('- '+item for item in items)+'\n\n'))
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
    ignored=set('the and for that this with will would should first second third fourth fifth sixth seventh eighth ninth tenth one are was were such okay then'.split())
    source_words={word.casefold() for word in re.findall(r'[^\W_]+',prepared) if len(word)>2 and word.casefold() not in ignored}
    flattened=''.join(char.casefold() for char in result if char.isalnum())
    if source_words and sum(word in flattened for word in source_words)/len(source_words)<.8:return False
    offset=0
    for item in anchors:
        pattern=r'(?<!\w)'+literal_pattern(item.strip(' .!?'))+r'(?!\w)'
        found=next((i for i in range(offset,len(output_items)) if re.search(pattern,output_items[i],re.I)),None)
        if found is None:return False
        offset=found+1
    return True
