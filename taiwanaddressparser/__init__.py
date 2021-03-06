import os
import pandas as pd

from .structures import AddrMap, Pca

__version__ = "0.0.5"
P, C, R = 0, 1, 2
pwd_path = os.path.abspath(os.path.dirname(__file__))
pcr_path = os.path.join(pwd_path, 'pcr.csv')


def _data_from_csv(pca_path: str):
    province_map = {}
    city_map = AddrMap()
    area_map = AddrMap()
    province_area_map = AddrMap()

    def _fill_province_map(province_map: dict, record_dict: dict):
        """
        填寫直轄市或省 - 第一級分類
        :param province_map:
        :param record_dict:
        :return: province_map
        """
        sheng = record_dict['sheng']
        if sheng not in province_map:
            province_map[sheng] = sheng
            # 省 和 直轄市
            if sheng.endswith('省') or sheng.endswith('市'):
                province_map[sheng[:-1]] = sheng

    def _fill_city_map(city_map: AddrMap, record_dict: dict):
        """
        填寫縣或省轄市 - 第二級分類
        :param city_map:
        :param record_dict:
        :return: city_map
        """
        city_name = record_dict['shi']
        pca_tuple = (record_dict['sheng'], record_dict['shi'], record_dict['qu'])
        city_map.append_relational_addr(city_name, pca_tuple, C)
        if city_name.endswith('市'):
            city_map.append_relational_addr(city_name[:-1], pca_tuple, C)

    def _fill_province_area_map(province_area_map: AddrMap, record_dict):
        """
        直轄市與區的連結
        :param province_area_map:
        :param record_dict:
        :return:
        """
        pca_tuple = (record_dict['sheng'], record_dict['shi'], record_dict['qu'])
        key = (record_dict['sheng'], record_dict['qu'])
        province_area_map.append_relational_addr(key, pca_tuple, P)

    def _fill_area_map(area_map: AddrMap, record_dict):
        """
        :param area_map: dict
        :param record_dict: dict
        :return: area_map
        """
        area_name = record_dict['qu']
        pca_tuple = (record_dict['sheng'], record_dict['shi'], record_dict['qu'])
        area_map.append_relational_addr(area_name, pca_tuple, R)

    with open(pca_path, encoding='utf-8')as f:
        import csv
        pca_csv = csv.DictReader(f)
        for record_dict in pca_csv:
            _fill_province_map(province_map, record_dict)
            _fill_area_map(area_map, record_dict)
            _fill_city_map(city_map, record_dict)
            _fill_province_area_map(province_area_map, record_dict)

    return province_map, city_map, area_map, province_area_map


province_map, city_map, region_map, province_area_map = _data_from_csv(pcr_path)



def transform(location_strs, index=None, cut=False, pos_sensitive=False):

    def _handle_one_record(addr, cut, pos_sensitive):

        def _extract_addr(addr, cut):
            return _jieba_extract(addr) if cut else _full_text_extract(addr)

        def _jieba_extract(addr):
            import jieba
            munis = {'臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市'}

            def is_munis(city_full_name: str):
                return city_full_name in munis

            result = Pca()
            pos = 0
            truncate = 0

            def _set_pca(pca_property, name, full_name):
                if not getattr(result, pca_property):
                    setattr(result, pca_property, full_name)
                    setattr(result, pca_property + "_pos", pos)
                    if is_munis(full_name):
                        setattr(result, "province_pos", pos)
                    nonlocal truncate
                    if pos == truncate:
                        truncate += len(name)

            for word in jieba.cut(addr):
                if word in city_map:
                    _set_pca('city', word, city_map.get_full_name(word))
                elif word in province_map:
                    _set_pca('province', word, province_map[word])

                pos += len(word)

            return result, addr[truncate:]

        if not isinstance(addr, str) or addr == '' or addr is None:
            empty = {'省': '', '市': '', '區': ''}
            if pos_sensitive:
                empty['省_pos'] = -1
                empty['市_pos'] = -1
                empty['區_pos'] = -1
            return empty

        def _fill_province(pca):
            if (not pca.province) and pca.city and (pca.city in city_map):
                pca.province = city_map.get_value(pca.city, P)

        def _fill_city(pca):
            if not pca.city:
                if pca.area:
                    if pca.area in region_map and region_map.is_unique_value(pca.area):
                        pca.city = region_map.get_value(pca.area, C)
                        return

                if pca.area and pca.province:
                    newKey = (pca.province, pca.area)
                    if newKey in province_area_map and province_area_map.is_unique_value(newKey):
                        pca.city = province_area_map.get_value(newKey, C)
                        return

        pca, left_addr = _extract_addr(addr, cut)
        _fill_city(pca)
        _fill_province(pca)

        result = pca.propertys_dict(pos_sensitive)
        result["地址"] = left_addr
        return result

    if index is None:
        index = []
    result = pd.DataFrame(
        [_handle_one_record(addr, cut, pos_sensitive) for addr in location_strs], index=index) \
        if index else pd.DataFrame([_handle_one_record(addr, cut, pos_sensitive) for addr in location_strs])
    if pos_sensitive:
        return result.loc[:, ('省', '市', '區', '地址', '省_pos', '市_pos', '區_pos')]
    else:
        return result.loc[:, ('省', '市', '區', '地址')]

def _full_text_extract(addr, lookahead):
    result = Pca()
    truncate = 0

    def _set_pca(pca_property, pos, name, full_name):

        def _defer_set():
            munis = {'臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市'}

            def is_munis(city_full_name: str):
                return city_full_name in munis

            if not getattr(result, pca_property):
                setattr(result, pca_property, full_name)
                setattr(result, pca_property + "_pos", pos)
                if is_munis(full_name):
                    setattr(result, "province_pos", pos)
                nonlocal truncate
                if pos == truncate:
                    truncate += len(name)
            return len(name)

        return _defer_set

    i = 0
    filter_address_chars = ['路', '街', '村', '里', '鄰']
    while i < len(addr):
        defer_fun = None
        for length in range(1, lookahead + 1):
            end_pos = i + length
            if end_pos > len(addr):
                break
            word = addr[i:end_pos]
            word_next = addr[end_pos] if end_pos < len(addr) else ''

            if word_next in filter_address_chars:
                continue
            elif word in region_map:
                defer_fun = _set_pca('area', i, word, region_map.get_full_name(word))
                continue
            elif word in city_map:
                defer_fun = _set_pca('city', i, word, city_map.get_full_name(word))
                continue
            elif word in province_map:
                defer_fun = _set_pca('province', i, word, province_map[word])
                continue

        if defer_fun:
            i += defer_fun()
        else:
            i += 1

    return result, addr[truncate:]