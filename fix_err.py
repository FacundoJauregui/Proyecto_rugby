import os

def fix_template(filepath):
    with open(filepath, 'rb') as f:
        t = f.read().decode('utf-8')

    # Reemplazo mas robusto por las dudas existan problemas de espacios
    import re
    pattern = r"\{%\s*if\s+field\.errors\s*%\}[\s\S]*?\{%\s*endif\s*%\}"
    
    new_err = '''{% if field.errors %}
                            <ul class="mt-1 text-xs text-red-600 dark:text-red-400 pl-4 list-disc">
                                {% for error in field.errors %}
                                    <li class="mt-0.5">{{ error }}</li>
                                {% endfor %}
                            </ul>
                        {% endif %}'''

    t = re.sub(pattern, new_err, t)

    with open(filepath, 'wb') as f:
        f.write(t.encode('utf-8'))

fix_template('player/templates/player/admin_user_form.html')
if os.path.exists('player/templates/player/coach_player_form.html'):
    fix_template('player/templates/player/coach_player_form.html')
