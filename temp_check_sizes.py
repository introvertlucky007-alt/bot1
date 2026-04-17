from pathlib import Path
base = Path('c:/VCBOT')
for folder in ['templates/IPL Legends', 'templates/WPL cards']:
    d = base / folder
    print('FOLDER', folder, 'exists', d.exists())
    if d.exists():
        sizes = []
        for p in sorted(d.glob('*.png')):
            sizes.append((p.name, p.stat().st_size, p.stat().st_size/1024, p.stat().st_size/1024/1024))
        print(folder, len(sizes))
        for name, size, kb, mb in sizes[:15]:
            print(name, f'{size} bytes', f'{kb:.1f} KB', f'{mb:.2f} MB')
        if len(sizes) > 15:
            print('...')
