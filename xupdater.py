from .apiwrapper import api_call
from .proloader import TusNetLoader
from .layout import *
from .utils.xcutils import *
# from .xcdb.xcdb import *
# from .domain import XcDomain
from .xcdb.zlmdb import *
from functools import partial
from .rdbasic import XcReaderBasic
from .rdprice import XcReaderPrice
from .utils.memoize import lazyval
from .proloader import netloader_init, TusNetLoader
from .domain import XcDomain

log = logbook.Logger('tupd')


class XcDBUpdater(XcReaderBasic, XcReaderPrice):
    """
    rollback: rollback data units to do integrity check when updating
    """

    master_db = None

    @lazyval
    def netloader(self) -> TusNetLoader:
        return netloader_init()

    def __init__(self, last_day=None, dbtype=DBTYPE.DB_LMDB):
        """
        :param last_day: Tushare last date with data available,
                            we assume yesterday's data is available in today.
        """
        if dbtype == DBTYPE.DB_LMDB:
            self.master_db = XcLMDB(LMDB_NAME, readonly=False)
            self.acc = XcLMDBAccessor
            self.facc = partial(XcLMDBAccessor, self.master_db)

            # , write_buffer_size = 0x400000, block_size = 0x4000,
            # max_file_size = 0x1000000, lru_cache_size = 0x100000, bloom_filter_bits = 0
        else:
            # self.master_db = XcLevelDB(LEVELDB_NAME, readonly=False)
            # self.acc = XcLevelDBAccessor
            # self.facc = partial(XcLevelDBAccessor, self.master_db)
            pass

        if last_day is None:
            """
            Last date always point to the end of Today. but tushare data may not exist at this time.
            """
            self.xctus_last_day = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
        else:
            self.xctus_last_day = last_day

        self.xctus_first_day = pd.Timestamp('20000101')

        log.info('Updater: date range:{}-{}'.format(self.xctus_first_day, self.xctus_last_day))

        super(XcDBUpdater, self).__init__()

    def init_domain(self):
        """
        because updater may working at multi thread env, so need to load info first.
        """
        super(XcDBUpdater, self).init_domain()
        # dummy read here to create the tcalmap, or it may fail when parallel thread case.
        aa = self.suspend_info
        aa = self.stock_info
        aa = self.index_info
        aa = self.fund_info
        aa = self.tcalmap_day
        aa = self.tcalmap_mon

    # def update_domain(self, force_mode=False):
    #     super(XcDBUpdater, self).update_domain(force_mode)
    #
    #     self.suspend_info = self.get_suspend_d(self.xctus_first_day, self.xctus_last_day)

    def update_suspend_d(self, start, end, rollback=10):
        """
        :param start:
        :param end:
        :param rollback:
        :return:
        """
        mmdts = self.gen_keys_daily(start, end, None, None)
        if mmdts is None:
            return

        bvalid = np.full((len(mmdts),), True, dtype=np.bool)
        db = self.facc(TusSdbs.SDB_SUSPEND_D.value, SUSPEND_D_META, readonly=True)
        for n, dd in enumerate(mmdts):
            dtkey = dt64_to_strdt(dd)
            val = db.load(dtkey, raw_mode=True)
            if val is not None:
                bvalid[n] = True  # update missed month data.
            else:
                bvalid[n] = False
        db.commit()

        if rollback > 0:
            # set tail to invalid to always download it
            bvalid[-rollback:] = False

        for n, dd in enumerate(mmdts):
            if not bvalid[n]:
                data = self.netloader.set_suspend_d(dd)
                dtkey = dt64_to_strdt(dd)
                db = self.facc(TusSdbs.SDB_SUSPEND_D.value, SUSPEND_D_META)
                db.save(dtkey, data)
                db.commit()

        return np.sum(~bvalid)

    def update_price_daily(self, code, start, end, astype, rollback=3):
        """

        :param code:
        :param start:
        :param end:
        :param astype:
        :param rollback:
        :return:
        """
        if astype is None:
            astype = self.asset_type(code)
        mmdts = self.gen_keys_monthly(start, end, code, astype)
        if mmdts is None:
            return 0

        db = self.facc(TusSdbs.SDB_DAILY_PRICE.value + code, EQUITY_DAILY_PRICE_META, readonly=True)
        bvalid = np.full((len(mmdts),), True, dtype=np.bool)

        for n, dd in enumerate(mmdts):
            dtkey = dt64_to_strdt(dd)
            val = db.load(dtkey, raw_mode=True)
            if val is not None:
                if n >= len(mmdts) - rollback:
                    bvalid[n] = self.integrity_check_km_vday(dd, val[:, 4], code, check_mode=1)
                else:
                    bvalid[n] = self.integrity_check_km_vday(dd, val[:, 4], code, check_mode=0)
            else:
                bvalid[n] = False
            # TODO: 数据缓存中最后一个数据，也应进行完整性检查。
        db.commit()
        count = np.sum(~bvalid)

        # 每次最大获取5000条记录
        max_units = 4700 // 23
        need_update = nadata_iter(bvalid, max_units)
        while True:
            tstart, tend = next(need_update)
            if tstart is None:
                break
            dts_upd = mmdts[tstart: tend + 1]
            data = self.netloader.set_price_daily(code, MONTH_START(dts_upd[0]), MONTH_END(dts_upd[-1]), astype)
            if data is None:
                continue
            data = data.set_index('trade_date', drop=True)
            data.index = pd.to_datetime(data.index, format=DATE_FORMAT)
            db = self.facc(TusSdbs.SDB_DAILY_PRICE.value + code, EQUITY_DAILY_PRICE_META)
            for tt in dts_upd:
                dtkey = dt64_to_strdt(tt)
                dayindex = self.gen_dindex_monthly(tt, tt)
                xxd = data.reindex(index=dayindex)
                db.save(dtkey, xxd)
            db.commit()
        return count

    def update_price_minute(self, code, start, end, freq='1min', astype='E', rollback=10):
        """
        :param code:
        :param start:
        :param end:
        :param freq:
        :param astype:
        :param rollback:
        :return:
        """
        if freq not in XTUS_FREQS:
            return 0

        if astype is None:
            astype = self.asset_type(code)
        mmdts = self.gen_keys_daily(start, end, code, astype)
        if mmdts is None:
            return 0

        bvalid = np.full((len(mmdts),), True, dtype=np.bool)
        db = self.facc((TusSdbs.SDB_MINUTE_PRICE.value + code + freq), EQUITY_MINUTE_PRICE_META, readonly=True)
        for n, dd in enumerate(mmdts):
            dtkey = dt64_to_strdt(dd)
            val = db.load(dtkey, raw_mode=True)
            if val is not None:
                if n >= len(mmdts) - rollback:
                    bvalid[n] = self.integrity_check_kd_vmin(dd, val[:, 4], freq=freq, code=code, check_mode=1)
                else:
                    bvalid[n] = self.integrity_check_kd_vmin(dd, val[:, 4], freq=freq, code=code, check_mode=0)
            else:
                bvalid[n] = False
        count = np.sum(~bvalid)
        db.commit()

        # 每次最大获取8000条记录
        cc = {'1min': 1, '5min': 5, '15min': 15, '30min': 30, '60min': 60}
        max_units = 6000 // (240 // cc[freq] + 1)
        need_update = nadata_iter(bvalid, max_units)
        while True:
            tstart, tend = next(need_update)
            if tstart is None:
                break
            dts_upd = mmdts[tstart: tend + 1]
            data = self.netloader.set_price_minute(code, dts_upd[0], dts_upd[-1], freq)
            if data is None:
                continue
            data = data.set_index('trade_time', drop=True)
            data.index = pd.to_datetime(data.index, format=DATETIME_FORMAT)
            db = self.facc((TusSdbs.SDB_MINUTE_PRICE.value + code + freq), EQUITY_MINUTE_PRICE_META)
            for tt in dts_upd:
                dtkey = dt64_to_strdt(tt)
                minindex = self.gen_mindex_daily(tt, tt, freq)
                xxd = data.reindex(index=minindex)
                if (xxd.volume == 0.0).all():
                    # 如果全天无交易，vol == 0, 则清空df.
                    xxd.loc[:, :] = np.nan
                db.save(dtkey, xxd)
            db.commit()

        return count

    def update_stock_adjfactor(self, code, start, end, rollback=3):
        """

        :param code:
        :param start:
        :param end:
        :return:
        """
        mmdts = self.gen_keys_monthly(start, end, code, 'E')
        if mmdts is None:
            return 0

        bvalid = np.full((len(mmdts),), True, dtype=np.bool)

        db = self.facc((TusSdbs.SDB_STOCK_ADJFACTOR.value + code), STOCK_ADJFACTOR_META, readonly=True)
        for n, dd in enumerate(mmdts):
            dtkey = dt64_to_strdt(dd)
            val = db.load(dtkey, raw_mode=True)
            if val is not None:
                if n >= len(mmdts) - rollback:
                    bvalid[n] = self.integrity_check_km_vday(dd, val[:, 0], code, check_mode=1)
                else:
                    bvalid[n] = self.integrity_check_km_vday(dd, val[:, 0], code, check_mode=0)
            else:
                bvalid[n] = False
        db.commit()
        count = np.sum(~bvalid)

        # 每次最大获取5000条记录
        max_units = 4000 // 23
        need_update = nadata_iter(bvalid, max_units)
        while True:
            tstart, tend = next(need_update)
            if tstart is None:
                break
            dts_upd = mmdts[tstart: tend + 1]
            data = self.netloader.set_stock_adjfactor(code, MONTH_START(dts_upd[0]), MONTH_END(dts_upd[-1]))
            if data is None:
                continue
            data = data.set_index('trade_date', drop=True)
            data.index = pd.to_datetime(data.index, format=DATE_FORMAT)
            db = self.facc((TusSdbs.SDB_STOCK_ADJFACTOR.value + code), STOCK_ADJFACTOR_META)
            for tt in dts_upd:
                dtkey = dt64_to_strdt(tt)
                dayindex = self.gen_dindex_monthly(tt, tt)
                xxd = data.reindex(index=dayindex)
                db.save(dtkey, xxd)
            db.commit()
        return count

    def update_stock_dayinfo(self, code, start, end, rollback=3):
        """

        :param code:
        :param start:
        :param end:
        :return:
        """
        mmdts = self.gen_keys_monthly(start, end, code, 'E')
        if mmdts is None:
            return 0

        db = self.facc((TusSdbs.SDB_STOCK_DAILY_INFO.value + code), STOCK_DAILY_INFO_META, readonly=True)
        bvalid = np.full((len(mmdts),), True, dtype=np.bool)
        for n, dd in enumerate(mmdts):
            dtkey = dt64_to_strdt(dd)
            val = db.load(dtkey, raw_mode=True)
            if val is not None:
                if n >= len(mmdts) - rollback:
                    bvalid[n] = self.integrity_check_km_vday(dd, val[:, 0], code, check_mode=1)
                else:
                    bvalid[n] = self.integrity_check_km_vday(dd, val[:, 0], code, check_mode=0)
            else:
                bvalid[n] = False
        db.commit()
        count = np.sum(~bvalid)

        # 每次最大获取5000条记录
        max_units = 4700 // 23
        need_update = nadata_iter(bvalid, max_units)
        while True:
            tstart, tend = next(need_update)
            if tstart is None:
                break
            dts_upd = mmdts[tstart: tend + 1]
            data = self.netloader.set_stock_daily_info(code, MONTH_START(dts_upd[0]), MONTH_END(dts_upd[-1]))
            if data is None:
                continue
            data = data.set_index('trade_date', drop=True)
            data.index = pd.to_datetime(data.index, format=DATE_FORMAT)
            db = self.facc((TusSdbs.SDB_STOCK_DAILY_INFO.value + code),
                           STOCK_DAILY_INFO_META)
            for tt in dts_upd:
                dtkey = dt64_to_strdt(tt)
                dayindex = self.gen_dindex_monthly(tt, tt)
                xxd = data.reindex(index=dayindex)
                db.save(dtkey, xxd)
            db.commit()
        return count

    def update_stock_xdxr(self, code, start, end):
        """
        update the stock xdxr, fill the prev_close column.
        :param code:
        :param start:
        :param end:
        :return:
        """
        data = self.netloader.set_stock_xdxr(code)
        if data is None:
            return

        price = self.get_price_daily(code, start, end)
        if price is None:
            return

        ffclose = price.close.ffill().shift(1)
        for n, row in data.iterrows():
            exdate = row['ex_date']
            if pd.isna(exdate):
                continue
            exdate = pd.Timestamp(exdate)
            if exdate not in ffclose.index:
                # log.info('miss price data:{}-{}'.format(code, exdate))
                continue
            data.loc[n, 'prev_close'] = ffclose.loc[exdate]

        db = self.facc(TusSdbs.SDB_STOCK_XDXR.value, STOCK_XDXR_META)
        db.save(code, data)
        db.commit()

        return data


g_updater: XcDBUpdater = None


def tusupdater_init() -> XcDBUpdater:
    global g_updater
    if g_updater is None:
        g_updater = XcDBUpdater()
        # try:
        g_updater.init_domain()
        # except:
        #     log.info('Init domain fail.')
        #     pass
    return g_updater
