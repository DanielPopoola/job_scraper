import logging

from django.core.management.base import BaseCommand

from scraper.pipeline.processor import JobProcessingPipeline


class Command(BaseCommand):
    help = 'run job processing pipeline'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--reprocess-failed',
            action='store_true',
            help='Reprocess jobs that have previously failed',
        )

        parser.add_argument(
            '--clear-jobs',
            action='store_true',
            help='Delete all jobs from the Job table before processing',
        )

        parser.add_argument(
            '--revert-all',
            action='store_true',
            help='Revert all job postings to pending status',
        )

    def handle(self, *args, **options):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        if options['clear_jobs']:
            from scraper.models import Job
            self.stdout.write('Deleting all jobs...')
            count, _ = Job.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} jobs.'))

        if options['revert_all']:
            from scraper.models import RawJobPosting
            self.stdout.write('Reverting all job postings to pending...')
            count = RawJobPosting.objects.update(processing_status='pending')
            self.stdout.write(self.style.SUCCESS(f'Successfully reverted {count} job postings.'))
            return

        pipeline = JobProcessingPipeline()

        if options['reprocess_failed']:
            stats = pipeline.reprocess_failed_jobs()
        else:
            stats = pipeline.process_pending_jobs()
        
        print("Pipeline processing completed:")
        print(f"  Processed: {stats['processed']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Duplicates found: {stats['duplicates_found']}")
        print(f"  New canonical jobs: {stats['new_canonical_jobs']}")
        
        # Show current database state
        from scraper.models import RawJobPosting
        
        print("\nDatabase status:")
        print(f"  Pending: {RawJobPosting.objects.filter(processing_status='pending').count()}")
        print(f"  Processed: {RawJobPosting.objects.filter(processing_status='processed').count()}")
        print(f"  Failed: {RawJobPosting.objects.filter(processing_status='failed').count()}")