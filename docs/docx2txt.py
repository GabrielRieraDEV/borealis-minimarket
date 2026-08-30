import sys, zipfile, xml.etree.ElementTree as ET
NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def text_of(el):
    return ''.join(n.text or '' for n in el.iter(NS + 't'))


for f in sys.argv[1:]:
    z = zipfile.ZipFile(f)
    root = ET.fromstring(z.read('word/document.xml'))
    body = root.find(NS + 'body')
    out = []
    for child in body:
        tag = child.tag
        if tag == NS + 'p':
            out.append(text_of(child))
        elif tag == NS + 'tbl':
            for tr in child.findall(NS + 'tr'):
                cells = [text_of(tc) for tc in tr.findall(NS + 'tc')]
                out.append(' | '.join(cells))
            out.append('')
    txt = '\n'.join(out)
    dest = f.rsplit('.', 1)[0] + '.txt'
    open(dest, 'w', encoding='utf-8').write(txt)
    print(dest, len(txt))
