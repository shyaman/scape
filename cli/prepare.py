import os
import pickle
import click
import pybedtools

from utils.isoform import Transcripts
from utils.utils import window

@click.command()
@click.option(
    '--gtf',
    type=str,
    help='The gtf (gz or not) file for preparing utr and intron region.',
    required=True
    )
@click.option(
    '--prefix',
    type=str,
    default='genes',
    help ='The prefix of output bed file.'
    )
@click.option(
    '--refseq',
    is_flag=True,
    default=False,
    help='Use refseq annotation, default is False.'
    )

def prepare(
    gtf,
    prefix,
    refseq
    ):
    if not all([gtf]):
        cli(['prepare', '--help'])
        sys.exit(1)
    

    utr_outfile = prefix + '_utr.bed'
    intron_outfile = prefix + '_intron.bed'
    gtf_prefix = os.path.splitext(os.path.abspath(gtf))[0]

    utr_out = open(utr_outfile, 'w')
    gene_db = '{}.pkl'.format(gtf_prefix)
    mt_id = set(['MT','CHRM'])
    if os.path.exists(gene_db):
        # if exsit, just read it
        struc = pickle.load(open(gene_db, 'rb'))
    else:
        # if not, prepare the transcript information
        struc = Transcripts(gtf).structure()
        pickle.dump(struc, open(gene_db, 'wb'))

    # prepare BedTool obj for exon line from gtf file
    gtf_fh = pybedtools.BedTool(gtf)
    exon_from_gtf = []
    for line in gtf_fh:
        line = str(line).split('\t')
        bio_type = line[2]
        if bio_type != 'exon':
            continue
        exon_from_gtf.append(
            '\t'.join([
                line[0],
                line[3],
                line[4],
                '.',
                '.',
                line[6]
            ]) + '\n'
        )

    exon_from_gtf = pybedtools.BedTool(
        ''.join(exon_from_gtf), 
        from_string=True
        )

    intron_lst = []
    # only keep these biotype, keep same with 10X, but not same to MCA.
    mt_lst = []
    genes_use = {'antisense', 'lincRNA', 'protein_coding'}
    for gid, tids in struc.items():
        for tid, info in tids.items():

            if not refseq:
                # for GENCODE reference
                if 'gene_type' in info:
                    gene_type_id = 'gene_type'
                    trans_type_id = 'transcript_type'
                elif 'gene_biotype' in info:
                    gene_type_id = 'gene_biotype'
                    trans_type_id = 'transcript_biotype'
            
                if info[gene_type_id] not in genes_use:
                    continue

                # remove intron retaintion isoforms
                try:
                    if info[trans_type_id] == 'retained_intron':
                        continue
                except TypeError:
                    pass
            else:
                # filter out MIR from refseq
                if info['gene_name'].startswith('MIR'):
                    continue

            if info['strand'] == '+':
                st, en, = info['exon'][-1]
            else:
                st, en, = info['exon'][0]
            line_info = [
                info['chrom'],
                str(st),
                str(en),
                # ';'.join([info[gene_type_id], gid, tid, info['gene_name']]),
                info['gene_name'],
                '.',
                info['strand']
            ]
            if info['chrom'].upper() in mt_id:
                mt_lst.append('\t'.join(line_info))
            else:
                utr_out.write('\t'.join(line_info) + '\n')

            # intron information
            try:
                exon_lst = info['exon']
                if len(exon_lst) == 1:
                    continue
                else:
                    for two_exons in window(exon_lst, 2):
                        intron_lst.append('\t'.join([
                            info['chrom'],
                            str(two_exons[0][1] + 1),
                            str(two_exons[1][0] - 1),
                            ';'.join(
                                [
                                    info['chrom'],
                                    gid,
                                    tid,
                                    info['gene_name']
                                ]
                            ),
                            '.',
                            info['strand']
                        ]))
            except KeyError:
                continue
    utr_out.close()

    """
    sort and merge utr region information
    """
    bedtmp = pybedtools.BedTool(utr_outfile)
    # bedtmp = bedtmp.sort().merge(d=500, s = True, c = 4, o = 'distinct', delim = ';')
    bedtmp = bedtmp.sort().merge(d=500, s = True, c = 4, o = 'distinct', delim = ';')
    utr_out = open(utr_outfile, 'w')
    for line in bedtmp:
        # write only if coloumn 4 is single gene
        if len(line[4].split(';')) == 1:
            utr_out.write(str(line))

    # utr_out.write(str(bedtmp))
    if mt_lst:
        mt_tmp = pybedtools.BedTool('\n'.join(mt_lst), from_string=True).sort().merge(s=True, c=4, o='distinct', delim=';')
        for line in mt_tmp:
            if len(line[4].split(';')) == 1:
                utr_out.write(str(line))
    utr_out.close()
