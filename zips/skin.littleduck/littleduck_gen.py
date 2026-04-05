
import sys
import argparse

# Constants based on skin.littleduck style
DEFAULT_COLORS = {
    "focus": "button_focus",
    "unfocused": "unfocused_text",
    "accent": "accent_color",
    "text": "white"
}

TEMPLATES = {
    "widget": """
    <include content="{widget_type}">
        <param name="content_path" value="{content_path}"/>
        <param name="widget_header" value="{header}"/>
        <param name="widget_target" value="{target}"/>
        <param name="list_id" value="{list_id}"/>
        <param name="fallback_icon" value="{fallback_icon}"/>
    </include>""",
    
    "variable": """
    <variable name="{var_name}">
        <value condition="{condition}">{value1}</value>
        <value>{value2}</value>
    </variable>""",

    "label": """
    <control type="label">
        <left>{left}</left>
        <top>{top}</top>
        <width>{width}</width>
        <height>{height}</height>
        <font>{font}</font>
        <textcolor>{color}</textcolor>
        <label>{label}</label>
        <shadowcolor>text_shadow</shadowcolor>
    </control>"""
}

def gen_widget(widget_type, content_path, header, target, list_id, fallback_icon):
    # Mapping friendly names to skin includes
    mapping = {
        "poster": "WidgetListPoster",
        "big_poster": "WidgetListBigPoster",
        "landscape": "WidgetListLandscape",
        "big_landscape": "WidgetListBigLandscape",
        "square": "WidgetListSquare",
        "category": "WidgetListCategory",
        "episodes": "WidgetListEpisodes"
    }
    w_type = mapping.get(widget_type, widget_type)
    return TEMPLATES["widget"].format(
        widget_type=w_type,
        content_path=content_path,
        header=header,
        target=target,
        list_id=list_id,
        fallback_icon=fallback_icon
    )

def main():
    parser = argparse.ArgumentParser(description='Little Duck XML Generator')
    subparsers = parser.add_subparsers(dest='command')

    # Widget command
    widget_parser = subparsers.add_parser('widget', help='Generate a widget include')
    widget_parser.add_argument('--type', choices=['poster', 'big_poster', 'landscape', 'big_landscape', 'square', 'category', 'episodes'], default='poster')
    widget_parser.add_argument('--path', required=True, help='Content path (e.g. plugin://...)')
    widget_parser.add_argument('--header', required=True, help='Widget label/header')
    widget_parser.add_argument('--target', default='videos', help='Navigation target')
    widget_parser.add_argument('--id', required=True, help='Unique list ID')
    widget_parser.add_argument('--icon', default='DefaultAddon.png', help='Fallback icon')

    # Label command
    label_parser = subparsers.add_parser('label', help='Generate a label control')
    label_parser.add_argument('--label', required=True)
    label_parser.add_argument('--left', default='0')
    label_parser.add_argument('--top', default='0')
    label_parser.add_argument('--width', default='auto')
    label_parser.add_argument('--height', default='40')
    label_parser.add_argument('--font', default='font13')
    label_parser.add_argument('--color', default='white')

    args = parser.parse_args()

    if args.command == 'widget':
        print(gen_widget(args.type, args.path, args.header, args.target, args.id, args.icon))
    elif args.command == 'label':
        print(TEMPLATES["label"].format(**vars(args)))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
