# encoding: utf-8
# CadHelper bridge for SketchUp (2017+).
# Listens on 127.0.0.1 only. Each request is one JSON line:
#   {"token": "...", "op": "eval"|"ping"|"info"|"build_scene", ...}
# and gets one JSON line back. The token is read from %USERPROFILE%\CadHelper\sketchup_token.txt
# so only the local CadHelper server can talk to it.
require 'socket'
require 'json'

module CadHelperBridge
  PORT = (ENV['CADHELPER_SKETCHUP_PORT'] || '47811').to_i
  # 설치 프로그램이 실제 위치로 바꿔 씁니다. (못 바꿨으면 흔한 위치를 차례로 찾음)
  HOME_INSTALLED = '@@CADHELPER_HOME@@'
  HOME = [HOME_INSTALLED, File.join(ENV['SystemDrive'] || 'C:', 'work', '.cadhelper'),
          File.join(ENV['USERPROFILE'] || Dir.home, 'CadHelper')].find { |d| !d.include?('@@') && File.exist?(File.join(d, 'sketchup_token.txt')) } ||
         File.join(ENV['USERPROFILE'] || Dir.home, 'CadHelper')
  TOKEN_FILE = File.join(HOME, 'sketchup_token.txt')

  def self.token
    @token ||= (File.read(TOKEN_FILE, encoding: 'UTF-8').strip rescue '')
  end

  def self.start
    return if @server
    @server = TCPServer.new('127.0.0.1', PORT)
    @timer = UI.start_timer(0.15, true) { poll }
    puts "[CadHelper] SketchUp bridge listening on 127.0.0.1:#{PORT}"
  rescue => e
    puts "[CadHelper] bridge not started: #{e.message}"
  end

  def self.poll
    return if @busy
    @busy = true
    loop do
      client = begin
        @server.accept_nonblock
      rescue IO::WaitReadable, Errno::EINTR
        nil
      end
      break unless client
      handle(client)
    end
  rescue => e
    puts "[CadHelper] poll error: #{e.message}"
  ensure
    @busy = false
  end

  def self.read_line(client, timeout = 5)
    buf = ''
    deadline = Time.now + timeout
    while Time.now < deadline
      begin
        chunk = client.read_nonblock(65536)
        buf << chunk
        break if buf.include?("\n")
      rescue IO::WaitReadable
        IO.select([client], nil, nil, 0.05)
      rescue EOFError
        break
      end
    end
    buf.force_encoding('UTF-8')
  end

  def self.handle(client)
    req = JSON.parse(read_line(client))
    resp =
      if token.empty? || req['token'] != token
        { 'ok' => false, 'error' => 'bad token' }
      else
        dispatch(req)
      end
    client.write(JSON.generate(resp) + "\n")
  rescue => e
    (client.write(JSON.generate({ 'ok' => false, 'error' => "#{e.class}: #{e.message}" }) + "\n") rescue nil)
  ensure
    (client.close rescue nil)
  end

  def self.dispatch(req)
    model = Sketchup.active_model
    case req['op']
    when 'ping'
      { 'ok' => true, 'result' => { 'version' => Sketchup.version, 'model' => (model ? model.path : ''),
                                    'title' => (model ? model.title : '') } }
    when 'info'
      { 'ok' => true, 'result' => info(model) }
    when 'eval'
      result = nil
      model.start_operation(req['label'] || 'CadHelper', true)
      begin
        result = TOPLEVEL_BINDING.eval(req['code'].to_s)
        model.commit_operation
      rescue Exception => e
        model.abort_operation
        return { 'ok' => false, 'error' => "#{e.class}: #{e.message}", 'trace' => e.backtrace.first(5) }
      end
      { 'ok' => true, 'result' => result.inspect[0, 20000] }
    when 'build_scene'
      { 'ok' => true, 'result' => build_scene(model, req['path']) }
    when 'capture'
      view = model.active_view
      if req['iso']
        b = model.bounds
        c = b.center
        d = [b.width, b.height, b.depth].max
        eye = Geom::Point3d.new(c.x - d * 0.9, c.y - d * 1.1, c.z + d * 1.0)
        view.camera = Sketchup::Camera.new(eye, c, Z_AXIS)
      end
      view.zoom_extents if req['zoom'] || req['iso']
      ok = view.write_image(filename: req['path'], width: req['width'] || 1400, height: req['height'] || 900, antialias: true)
      { 'ok' => ok, 'result' => req['path'] }
    when 'save_copy'
      ok = model.save_copy(req['path'])
      { 'ok' => ok, 'result' => req['path'] }
    else
      { 'ok' => false, 'error' => "unknown op #{req['op']}" }
    end
  end

  # ---------------------------------------------------------------- info
  def self.walk(ents, tr, acc, path, tag, inherited = nil)
    ents.each do |e|
      case e
      when Sketchup::Face
        m = e.material || e.back_material || inherited
        key = m ? m.display_name : '(기본재질)'
        area = e.area(tr) * 0.00064516 # in^2 -> m^2
        acc[:mat][key] += area
        own = (e.layer.name rescue 'Layer0')
        t = (own == 'Layer0' || own == 'Untagged' || own.empty?) ? tag : own
        acc[:tag][t] += area
        n = e.normal.transform(tr)
        acc[:up][key] += area if n.length > 0 && n.normalize.z > 0.9
        acc[:faces] += 1
      when Sketchup::Group, Sketchup::ComponentInstance
        d = e.respond_to?(:definition) ? e.definition : e.entities.parent
        name = e.name.to_s.empty? ? d.name : e.name
        acc[:comp][e.is_a?(Sketchup::ComponentInstance) ? d.name : "그룹:#{name}"] += 1 if path.size < 2
        own = (e.layer.name rescue 'Layer0')
        child_tag = (own == 'Layer0' || own == 'Untagged' || own.empty?) ? tag : own
        walk(d.entities, tr * e.transformation, acc, path + [name], child_tag, e.material || inherited)
      end
    end
  end

  def self.info(model)
    acc = { mat: Hash.new(0.0), tag: Hash.new(0.0), up: Hash.new(0.0), comp: Hash.new(0), faces: 0 }
    walk(model.entities, Geom::Transformation.new, acc, [], '태그 없음')
    b = model.bounds
    {
      'title' => model.title, 'path' => model.path, 'version' => Sketchup.version,
      'size_m' => [b.width, b.height, b.depth].map { |v| (v * 0.0254).round(3) },
      'faces' => acc[:faces],
      'area_by_material_m2' => acc[:mat].select { |k, v| v >= 0.01 }.map { |k, v| [k, v.round(3)] }.sort_by { |x| -x[1] },
      'area_up_by_material_m2' => acc[:up].select { |k, v| v >= 0.01 }.map { |k, v| [k, v.round(3)] }.sort_by { |x| -x[1] },
      'area_by_tag_m2' => acc[:tag].select { |k, v| v >= 0.01 }.map { |k, v| [k, v.round(3)] }.sort_by { |x| -x[1] },
      'components_top_level' => acc[:comp].sort_by { |x| -x[1] }.first(200),
      'tags' => model.layers.map { |l| [l.name, l.visible?] },
      'selection_count' => model.selection.length
    }
  end

  # ---------------------------------------------------------- build scene
  def self.rgb(hex)
    h = hex.to_s.sub('#', '')
    h = 'cccccc' unless h =~ /\A\h{6}\z/
    Sketchup::Color.new(h[0, 2].to_i(16), h[2, 2].to_i(16), h[4, 2].to_i(16))
  end

  def self.mm(v)
    v.to_f.mm
  end

  def self.prism(ents, pts, z0, z1)
    pts = pts[0..-2] if pts.length > 3 && pts.first == pts.last
    base = pts.map { |x, y| Geom::Point3d.new(mm(x), mm(y), mm(z0)) }
    face = ents.add_face(base)
    return unless face
    h = z1.to_f - z0.to_f
    face.reverse! if face.normal.z < 0
    face.pushpull(mm(h)) if h.abs > 0.01
  end

  def self.build_scene(model, path)
    data = JSON.parse(File.read(path, encoding: 'bom|utf-8'))
    model.start_operation('CadHelper 3D 생성', true)
    tags = {}
    (data['layers'] || []).each do |l|
      t = model.layers.add(l['name'] || l['id'])
      t.visible = l['visible'] != false
      tags[l['id']] = t
    end
    mats = {}
    root = model.entities.add_group
    root.name = data['title'] || 'CadHelper 3D'
    n = 0
    (data['objects'] || []).each do |o|
      kind = o['kind']
      next if kind == 'label'
      g = root.entities.add_group
      g.name = o['name'].to_s
      g.layer = tags[o['layer']] if tags[o['layer']]
      col = o['color'] || '#cccccc'
      alpha = (o['opacity'] && o['opacity'].to_f < 1) ? o['opacity'].to_f : 1.0
      key = "#{o['material']}|#{col}|#{alpha}"
      mat = mats[key] ||= begin
        # readable names for quantity take-off: the material preset ("강마루"), else the colour
        base = o['material'].to_s.empty? ? "색_#{col.sub('#', '')}" : o['material'].to_s
        name = base
        existing = model.materials[name]
        if existing && (existing.color.to_i != rgb(col).to_i || (existing.alpha - alpha).abs > 0.01)
          name = "#{base}_#{col.sub('#', '')}"
          existing = model.materials[name]
        end
        m = existing || model.materials.add(name)
        m.color = rgb(col)
        m.alpha = alpha if alpha < 1
        m
      end
      case kind
      when 'box'
        prism(g.entities, [[o['x0'], o['y0']], [o['x1'], o['y0']], [o['x1'], o['y1']], [o['x0'], o['y1']]], o['z0'], o['z1'])
      when 'prism'
        prism(g.entities, o['points'], o['z0'], o['z1'])
      when 'wall'
        pts = o['path']
        pts = pts + [pts.first] if o['closed']
        t = (o['thickness'] || 100).to_f / 2.0
        pts.each_cons(2) do |a, b|
          dx = b[0] - a[0]; dy = b[1] - a[1]; len = Math.sqrt(dx * dx + dy * dy)
          next if len < 1
          ux = dx / len * t; uy = dy / len * t
          nx = -uy; ny = ux
          a2 = [a[0] - ux, a[1] - uy]; b2 = [b[0] + ux, b[1] + uy]
          seg = g.entities.add_group
          prism(seg.entities, [[a2[0] + nx, a2[1] + ny], [b2[0] + nx, b2[1] + ny], [b2[0] - nx, b2[1] - ny], [a2[0] - nx, a2[1] - ny]], o['z0'], o['z1'])
          seg.entities.grep(Sketchup::Face).each { |f| f.material = mat; f.back_material = mat }
        end
      end
      g.entities.grep(Sketchup::Face).each { |f| f.material = mat; f.back_material = mat }
      g.set_attribute('cadhelper', 'info', o['info'].to_s) if o['info']
      n += 1
    end
    model.commit_operation
    model.active_view.zoom_extents
    "#{n}개 객체 생성"
  rescue => e
    model.abort_operation rescue nil
    raise e
  end
end

CadHelperBridge.start unless file_loaded?(__FILE__)
file_loaded(__FILE__)
