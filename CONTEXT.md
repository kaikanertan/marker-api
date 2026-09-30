# Marker API

把 PDF 文档转换为 Markdown 的服务,并对转换结果做缓存,避免重复转换同一份内容。

## Language

**Conversion**:
把一份 PDF 按指定的 **Conversion Options** 转成 Markdown、元数据和图片的一次处理。
_Avoid_: Parse, job, task

**Conversion Result**:
一次 **Conversion** 的产物,包含 Markdown 文本、元数据、图片和处理耗时。
_Avoid_: Response, output

**Conversion Options**:
决定 **Conversion Result** 内容的参数:页数上限(`max_pages`)、起始页(`start_page`)、语言(`langs`)。
_Avoid_: Settings, params

**Performance Hint**:
只影响转换速度和显存占用、不影响 **Conversion Result** 内容的参数(`batch_multiplier`)。它不属于 **Conversion Options**。
_Avoid_: Option

**Upload Name**:
客户端上传时携带的文件名。它只用于日志和返回值展示,不代表文档的身份,也不参与缓存。
_Avoid_: Document name, file id

**Content Identity**:
一份 PDF 由其字节内容决定的身份。内容相同即视为同一份文档,与 **Upload Name** 无关。
_Avoid_: File name, path

## Caching

**Conversion Cache**:
按 **Cache Key** 保存 **Conversion Result** 的存储,命中时直接复用而不重新转换。
_Avoid_: Store, memo

**Cache Key**:
**Content Identity** 加上全部 **Conversion Options** 的组合。**Upload Name** 和 **Performance Hint** 不在其中。
_Avoid_: Cache path, cache filename

**Cache Hit**:
请求的 **Cache Key** 已存在于 **Conversion Cache**。命中时返回的 **Conversion Result** 携带本次请求的 **Upload Name**,而不是首次转换时的名字。
_Avoid_: Cached response
