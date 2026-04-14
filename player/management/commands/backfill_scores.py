import re
from django.core.management.base import BaseCommand
from player.models import Match


def _parse_score(marcador: str):
    if not marcador:
        return None, None
    m = re.match(r'^\s*(\d+)\s*-\s*(\d+)\s*$', marcador.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


class Command(BaseCommand):
    help = 'Rellena home_score/away_score de partidos existentes leyendo marcador_final de sus jugadas.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Sobreescribir marcadores aunque ya tengan valor.',
        )

    def handle(self, *args, **options):
        force = options['force']
        qs = Match.objects.prefetch_related('plays')
        if not force:
            qs = qs.filter(home_score__isnull=True)

        updated = 0
        skipped = 0

        for match in qs:
            # Buscar el último marcador_final no vacío en las jugadas
            last_marcador = (
                match.plays
                .exclude(marcador_final='')
                .order_by('inicio')
                .values_list('marcador_final', flat=True)
                .last()
            )
            home, away = _parse_score(last_marcador)
            if home is None:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'  Sin marcador parseable: {match} (marcador_final="{last_marcador}")'
                    )
                )
                continue

            match.home_score = home
            match.away_score = away
            match.save(update_fields=['home_score', 'away_score'])
            updated += 1
            self.stdout.write(
                self.style.SUCCESS(f'  Actualizado: {match}  →  {home} - {away}')
            )

        self.stdout.write(f'\nTotal actualizados: {updated} | Sin datos: {skipped}')
